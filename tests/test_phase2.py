"""
Tests for Phase 2: LangGraph Leave Workflow, LLM Extraction, and Human-in-the-Loop Resumption.
"""

import os
import pytest
from db.database import init_db, get_db_connection
from db.seed import seed_database
from agent.prompts import extract_fallback_rules, clean_llm_json
from agent.graph import run_leave_workflow, resume_workflow
from agent.tools import check_leave_balance

TEST_DB = "test_flowpilot_phase2.db"


@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    """Setup and teardown a clean test SQLite database."""
    import gc
    gc.collect()

    monkeypatch.setenv("FLOWPILOT_DB_PATH", TEST_DB)
    monkeypatch.setenv("FLOWPILOT_TEST_MODE", "true")

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


def test_leave_extraction_rules():
    """Verify regex/fallback parser extracts leave details accurately."""
    sample = "I need 3 days annual leave from Nov 10 for vacation"
    result = extract_fallback_rules(sample, "Engineering")
    assert result["workflow_type"] == "leave"
    assert result["extracted_data"]["days"] == 3
    assert result["extracted_data"]["leave_type"] == "annual"


def test_leave_workflow_pauses_for_approval():
    """Verify leave workflow runs steps 1 & 2, then pauses awaiting human approval."""
    req_text = "I need 2 days casual leave starting tomorrow"
    state = run_leave_workflow(raw_text=req_text, employee_id="EMP001")

    assert state["workflow_type"] == "leave"
    assert state["status"] == "pending_approval"
    assert state["current_step"] == "manager_approval"
    assert state["approval_decision"] == "PENDING"
    assert state["request_id"].startswith("REQ-")

    # Verify request is recorded in DB as pending_approval
    conn = get_db_connection(TEST_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT status, current_step FROM requests WHERE id = ?", (state["request_id"],))
    row = cursor.fetchone()
    assert row["status"] == "pending_approval"
    assert row["current_step"] == "manager_approval"

    # Verify audit log contains classification and approval request
    cursor.execute("SELECT COUNT(*) FROM audit_log WHERE request_id = ?", (state["request_id"],))
    count = cursor.fetchone()[0]
    assert count >= 2
    conn.close()


def test_leave_workflow_resume_approved():
    """Verify resuming a pending leave request with APPROVAL deducts balance and notifies employee."""
    req_text = "I need 2 days annual leave from Nov 5"
    state = run_leave_workflow(raw_text=req_text, employee_id="EMP001")
    req_id = state["request_id"]

    # Initial balance for EMP001 annual leave is 12
    initial_bal = check_leave_balance("EMP001", db_path=TEST_DB)
    assert initial_bal["annual_leave"] == 12

    # Resume with approval
    final_state = resume_workflow(request_id=req_id, decision="APPROVED", comments="Approved by manager")

    assert final_state["status"] == "completed"
    assert final_state["current_step"] == "completed"

    # Check leave balance deducted: 12 - 2 = 10
    updated_bal = check_leave_balance("EMP001", db_path=TEST_DB)
    assert updated_bal["annual_leave"] == 10

    # Verify notification sent to EMP001
    conn = get_db_connection(TEST_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT message FROM notifications WHERE employee_id = 'EMP001' AND request_id = ?", (req_id,))
    notif = cursor.fetchone()
    assert notif is not None
    assert "APPROVED" in notif["message"]
    conn.close()


def test_leave_workflow_resume_rejected():
    """Verify resuming with REJECTION does not deduct balance and notifies with rejection reason."""
    req_text = "I need 1 day sick leave"
    state = run_leave_workflow(raw_text=req_text, employee_id="EMP001")
    req_id = state["request_id"]

    initial_bal = check_leave_balance("EMP001", db_path=TEST_DB)["sick_leave"]

    final_state = resume_workflow(request_id=req_id, decision="REJECTED", comments="Critical sprint deadline")

    assert final_state["status"] == "rejected"
    assert final_state["current_step"] == "completed"

    # Balance should NOT have changed
    after_bal = check_leave_balance("EMP001", db_path=TEST_DB)["sick_leave"]
    assert after_bal == initial_bal

    # Check notification recorded rejection reason
    conn = get_db_connection(TEST_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT message FROM notifications WHERE employee_id = 'EMP001' AND request_id = ?", (req_id,))
    notif = cursor.fetchone()
    assert notif is not None
    assert "REJECTED" in notif["message"]
    assert "Critical sprint deadline" in notif["message"]
    conn.close()
