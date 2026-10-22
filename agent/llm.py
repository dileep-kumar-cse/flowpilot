"""
FlowPilot LLM Client Module
Provides resilient LLM calling with:
- Google Gemini API (Free tier flash models)
- Automatic model fallback on 404/503/high-demand errors
- Local Ollama fallback option
- Rule-based parser fallback if network/API is completely down
"""

import os
import time
import json
import requests
from typing import Dict, Any, Optional
from dotenv import load_dotenv

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from agent.prompts import SYSTEM_PROMPT, clean_llm_json, extract_fallback_rules

load_dotenv()

# Priority order of free flash models
FALLBACK_MODELS = [
    os.getenv("LLM_MODEL", "gemini-3.5-flash-lite"),
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.8-flash",
    "gemini-flash-latest"
]


def call_ollama(prompt: str, system_prompt: str = SYSTEM_PROMPT) -> Optional[str]:
    """Fallback to local Ollama instance if available."""
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model = os.getenv("OLLAMA_MODEL", "llama3")
    try:
        resp = requests.post(
            f"{base_url}/api/generate",
            json={"model": model, "prompt": f"{system_prompt}\n\nUser Request: {prompt}", "stream": False},
            timeout=10
        )
        if resp.status_code == 200:
            return resp.json().get("response")
    except Exception:
        pass
    return None


def extract_content_text(content: Any) -> str:
    """Extracts raw text string from LangChain response content (handles str, list, dict)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(item["text"])
        return "\n".join(parts)
    return str(content)


def classify_and_extract_request(
    user_text: str,
    employee_department: str = "Engineering",
    max_retries: int = 2
) -> Dict[str, Any]:
    """
    Analyzes plain-English user request, classifies workflow type ('leave' or 'purchase'),
    and extracts structured JSON payload with retries and fallbacks.
    """
    if os.getenv("FLOWPILOT_TEST_MODE", "false").lower() == "true":
        return extract_fallback_rules(user_text, employee_dept=employee_department)

    api_key = os.getenv("GEMINI_API_KEY")
    use_ollama = os.getenv("USE_OLLAMA_FALLBACK", "false").lower() == "true"

    # 1. Try Gemini API if API key exists
    if api_key:
        seen_models = set()
        for model_name in FALLBACK_MODELS:
            if model_name in seen_models:
                continue
            seen_models.add(model_name)

            for attempt in range(max_retries):
                try:
                    llm = ChatGoogleGenerativeAI(
                        model=model_name,
                        google_api_key=api_key,
                        temperature=0.1,
                        timeout=15
                    )
                    messages = [
                        SystemMessage(content=SYSTEM_PROMPT),
                        HumanMessage(content=f"Employee Department: {employee_department}\nUser Request: {user_text}")
                    ]
                    response = llm.invoke(messages)
                    raw_text = extract_content_text(response.content)
                    parsed_json = clean_llm_json(raw_text)
                    return parsed_json
                except Exception as e:
                    err_msg = str(e)
                    # If high demand or unavailable or not found, try next candidate model
                    if "503" in err_msg or "404" in err_msg or "UNAVAILABLE" in err_msg or "NOT_FOUND" in err_msg:
                        break  # Break inner loop, move to next model in FALLBACK_MODELS
                    time.sleep(1)

    # 2. Try Ollama if enabled or configured
    if use_ollama:
        ollama_resp = call_ollama(user_text, SYSTEM_PROMPT)
        if ollama_resp:
            try:
                return clean_llm_json(ollama_resp)
            except Exception:
                pass

    # 3. Rule-based extraction fallback (guarantees zero crashes)
    return extract_fallback_rules(user_text, employee_dept=employee_department)
