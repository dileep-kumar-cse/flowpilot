"""
Tests for Phase 5: Error Handling, Edge Cases, and Resiliency.
"""

import os
import pytest
from db.database import init_db, get_db_connection
from db.seed import seed_database
from agent.prompts import clean_llm_json, extract_fallback_rules
from agent.graph import run_workflow, resume_workflow
from agent.tools import check_leave_balance, check_budget

TEST_DB = "test_flowpilot_phase5.db"


@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    """Setup and teardown a clean test SQLite database."""
    import gc
    gc.collect()

    monkeypatch.setenv("FLOWPILOT_DB_PATH", TEST_DB)

    if os.path.exists(TEST_DB):
        try:
            os.remove(TEST_DB)
        except OSError:
            pass

    seed_database(TEST_DB)

    yield

    gc.collect()
    if os.path.exists(TEST_DB):
        try:
            os.remove(TEST_DB)
        except OSError:
            pass


def test_clean_llm_json_handles_markdown_and_noise():
    """Verify JSON extractor cleanly extracts valid dict from noisy markdown."""
    noisy_input = "Here is the result:\n```json\n{\"workflow_type\": \"leave\", \"days\": 2}\n```\nHope that helps!"
    parsed = clean_llm_json(noisy_input)
    assert parsed["workflow_type"] == "leave"
    assert parsed["days"] == 2


def test_clean_llm_json_invalid_raises():
    """Verify clean_llm_json raises ValueError on completely invalid text."""
    with pytest.raises(Exception):
        clean_llm_json("Not a json at all")


def test_unknown_workflow_routes_to_completion_with_message():
    """Verify ambiguous requests are classified as unknown and handled without crashing."""
    text = "Tell me a joke about workflow agents"
    state = run_workflow(raw_text=text, employee_id="EMP001")
    assert state["workflow_type"] == "unknown"
    assert state["status"] == "completed"

    # Notification sent
    conn = get_db_connection(TEST_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT message FROM notifications WHERE employee_id = 'EMP001' AND request_id = ?", (state["request_id"],))
    notif = cursor.fetchone()
    assert notif is not None
    conn.close()


def test_resume_non_existent_request_raises_error():
    """Verify resume_workflow gracefully raises ValueError for non-existent request ID."""
    with pytest.raises(ValueError, match="not found"):
        resume_workflow(request_id="REQ-NONEXISTENT", decision="APPROVED")


def test_budget_check_invalid_department():
    """Verify check_budget handles non-existent departments safely."""
    res = check_budget("NonExistentDept", 500.0, db_path=TEST_DB)
    assert res["success"] is False
    assert res["has_budget"] is False
    assert "not found" in res["error"].lower()


def test_leave_balance_invalid_employee():
    """Verify check_leave_balance handles non-existent employee safely."""
    res = check_leave_balance("EMP_GHOST", db_path=TEST_DB)
    assert res["success"] is False
    assert "not found" in res["error"].lower() or "no leave" in res["error"].lower()
