import pytest

from agent import graph
from agent.prompts import extract_fallback_rules


@pytest.fixture(autouse=True)
def mock_llm_classifier(monkeypatch):
    """Keep workflow tests deterministic and independent of external LLM APIs."""

    def classify_request(user_text, employee_department="Engineering", max_retries=2):
        return extract_fallback_rules(user_text, employee_dept=employee_department)

    monkeypatch.setattr(graph, "classify_and_extract_request", classify_request)
