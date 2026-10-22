"""
FlowPilot Prompts and Extraction Logic
Defines system instructions, few-shot examples, JSON schemas,
and fallback rule-based extractors for plain-English requests.
"""

import re
import json
from typing import Dict, Any, Optional

SYSTEM_PROMPT = """You are FlowPilot, an intelligent autonomous business workflow orchestrator.
Your job is to read an employee's plain-English message, classify the requested workflow,
and extract structured fields into strict JSON format.

Supported Workflows:
1. "leave": Employee requesting time off (annual, sick, or casual leave).
   Fields required:
   - "days" (int): Number of leave days requested.
   - "start_date" (str): Date when leave starts (e.g. '2026-11-05' or 'Nov 5').
   - "leave_type" (str): One of 'annual', 'sick', 'casual'. Default to 'annual' if unspecified.
   - "reason" (str): Purpose or note for the leave.

2. "purchase": Employee requesting equipment, software, or supplies requiring departmental budget.
   Fields required:
   - "department" (str): Department (e.g. 'Engineering', 'Marketing', 'HR', 'Finance').
   - "item" (str): Item or service name requested.
   - "amount" (float): Monetary cost in USD.
   - "reason" (str): Business justification.

If the request is ambiguous or unsupported, set workflow_type to "unknown".

Return ONLY a valid JSON object with the following schema, and no other text or explanation:
{
  "workflow_type": "leave" | "purchase" | "unknown",
  "confidence": 0.95,
  "summary": "Brief 1-sentence summary",
  "extracted_data": { ... }
}
"""


def extract_fallback_rules(text: str, employee_dept: str = "Engineering") -> Dict[str, Any]:
    """
    Deterministic rule-based extraction fallback if LLM is unavailable or rate-limited.
    Ensures 100% system availability without crashing.
    """
    text_lower = text.lower()
    
    # Check for leave keywords
    if any(k in text_lower for k in ["leave", "day off", "days off", "vacation", "sick"]):
        # Extract days
        days = 1
        days_match = re.search(r"(\d+)\s*(?:day|days)", text_lower)
        if days_match:
            days = int(days_match.group(1))
        
        # Extract leave type
        leave_type = "annual"
        if "sick" in text_lower:
            leave_type = "sick"
        elif "casual" in text_lower:
            leave_type = "casual"
            
        # Extract date
        start_date = "immediate"
        date_match = re.search(r"(?:from|on|starting)\s+([A-Za-z0-9\s,\-]+?)(?:\.|$|for|due)", text, re.IGNORECASE)
        if date_match:
            start_date = date_match.group(1).strip()
            
        return {
            "workflow_type": "leave",
            "confidence": 0.85,
            "summary": f"{days} days {leave_type} leave starting {start_date}",
            "extracted_data": {
                "days": days,
                "start_date": start_date,
                "leave_type": leave_type,
                "reason": text.strip()
            }
        }
        
    # Check for purchase keywords
    if any(k in text_lower for k in ["buy", "purchase", "order", "laptop", "monitor", "software", "license", "$"]):
        amount = 0.0
        amount_match = re.search(r"\$\s*(\d+(?:,\d+)?(?:\.\d+)?)", text)
        if not amount_match:
            amount_match = re.search(r"(?:costing|cost|price|for)\s+\$?\s*(\d+(?:,\d+)?(?:\.\d+)?)", text, re.IGNORECASE)
        if not amount_match:
            amount_match = re.search(r"(\d+(?:,\d+)?(?:\.\d+)?)\s*(?:usd|dollars)", text, re.IGNORECASE)
        if amount_match:
            amount = float(amount_match.group(1).replace(",", ""))
            
        item_match = re.search(r"(?:buy|purchase|order|need|for)\s+([a-zA-Z0-9\s\-]+?)(?:\s+for|\s+costing|\s+\$|\.|$)", text, re.IGNORECASE)
        item = item_match.group(1).strip() if item_match else "Office Equipment"
        
        return {
            "workflow_type": "purchase",
            "confidence": 0.85,
            "summary": f"Purchase request for {item} (${amount})",
            "extracted_data": {
                "department": employee_dept,
                "item": item,
                "amount": amount,
                "reason": text.strip()
            }
        }
        
    return {
        "workflow_type": "unknown",
        "confidence": 0.3,
        "summary": "Could not recognize workflow type",
        "extracted_data": {}
    }


def clean_llm_json(raw_text: str) -> Dict[str, Any]:
    """
    Cleans markdown formatting (```json ... ```) from LLM output and parses JSON.
    """
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    
    # Try finding the first '{' and last '}'
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1:
        cleaned = cleaned[first_brace:last_brace + 1]
        
    return json.loads(cleaned)
