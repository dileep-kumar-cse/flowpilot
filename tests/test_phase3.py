"""
Tests for Phase 3: Purchase Workflow, Finance Budget Checks, and Pause/Resume.
"""

import os
import pytest
from db.database import init_db, get_db_connection
from db.seed import seed_database
from agent.prompts import extract_fallback_rules
from agent.graph import run_workflow, run_purchase_workflow, resume_workflow
from agent.tools import check_budget

TEST_DB = "test_flowpilot_phase3.db"


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


def test_purchase_extraction_rules():
    """Verify purchase extraction identifies item, amount, and department."""
    text = "We need to purchase 2 Dell 4K Monitors for $800 for the Engineering team"
    res = extract_fallback_rules(text, employee_dept="Engineering")
    assert res["workflow_type"] == "purchase"
    assert res["extracted_data"]["amount"] == 800.0
    assert "Dell 4K Monitors" in res["extracted_data"]["item"] or "Monitors" in res["extracted_data"]["item"]


def test_purchase_workflow_pauses_for_approval():
    """Verify purchase workflow creates request and pauses awaiting Manager approval."""
    req_text = "Purchase a new MacBook Pro for $2500"
    state = run_purchase_workflow(raw_text=req_text, employee_id="EMP001")

    assert state["workflow_type"] == "purchase"
    assert state["status"] == "pending_approval"
    assert state["current_step"] == "manager_approval"
    assert state["approval_decision"] == "PENDING"
    assert state["request_id"].startswith("REQ-")

    # Verify pending state in database
    conn = get_db_connection(TEST_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT status, current_step FROM requests WHERE id = ?", (state["request_id"],))
    row = cursor.fetchone()
    assert row["status"] == "pending_approval"
    assert row["current_step"] == "manager_approval"
    conn.close()


def test_purchase_workflow_approved_with_budget():
    """Verify approved purchase request deducts departmental budget and sends confirmation."""
    req_text = "Order testing devices for $1500"
    state = run_purchase_workflow(raw_text=req_text, employee_id="EMP001")
    req_id = state["request_id"]

    # Initial Engineering budget remaining is 38,000
    initial_budget = check_budget("Engineering", 0.0, db_path=TEST_DB)["remaining_budget"]
    assert initial_budget == 38000.0

    # Resume with approval
    final_state = resume_workflow(request_id=req_id, decision="APPROVED", comments="Approved by engineering manager")

    assert final_state["status"] == "completed"
    assert final_state["current_step"] == "completed"

    # Verify budget deducted: 38000 - 1500 = 36500
    after_budget = check_budget("Engineering", 0.0, db_path=TEST_DB)["remaining_budget"]
    assert after_budget == 36500.0

    # Verify notification sent to employee
    conn = get_db_connection(TEST_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT message FROM notifications WHERE employee_id = 'EMP001' AND request_id = ?", (req_id,))
    notif = cursor.fetchone()
    assert notif is not None
    assert "APPROVED" in notif["message"]
    assert "Finance" in notif["message"]
    conn.close()


def test_purchase_workflow_insufficient_budget():
    """Verify approved purchase with excessive amount fails budget check and notifies employee."""
    # Marketing department only has $1500 remaining in seed data
    # Eve Wilson (EMP005) is in Marketing
    req_text = "Purchase enterprise software license for $10000"
    state = run_purchase_workflow(raw_text=req_text, employee_id="EMP005")
    req_id = state["request_id"]

    initial_budget = check_budget("Marketing", 0.0, db_path=TEST_DB)["remaining_budget"]

    # Manager approves, but budget check will fail
    final_state = resume_workflow(request_id=req_id, decision="APPROVED", comments="Approved if budget allows")

    assert final_state["status"] == "failed"
    assert "Insufficient budget" in final_state["error_message"]

    # Budget should NOT have changed
    after_budget = check_budget("Marketing", 0.0, db_path=TEST_DB)["remaining_budget"]
    assert after_budget == initial_budget

    # Notification should explain the failure
    conn = get_db_connection(TEST_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT message FROM notifications WHERE employee_id = 'EMP005' AND request_id = ?", (req_id,))
    notif = cursor.fetchone()
    assert notif is not None
    assert "could not be completed" in notif["message"]
    assert "Insufficient budget" in notif["message"]
    conn.close()


def test_purchase_workflow_rejected():
    """Verify rejected purchase request does not deduct budget and notifies employee."""
    req_text = "Purchase ergonomic office chair for $500"
    state = run_purchase_workflow(raw_text=req_text, employee_id="EMP001")
    req_id = state["request_id"]

    initial_budget = check_budget("Engineering", 0.0, db_path=TEST_DB)["remaining_budget"]

    final_state = resume_workflow(request_id=req_id, decision="REJECTED", comments="Not an essential business expense")

    assert final_state["status"] == "rejected"
    assert final_state["current_step"] == "completed"

    # Budget unchanged
    after_budget = check_budget("Engineering", 0.0, db_path=TEST_DB)["remaining_budget"]
    assert after_budget == initial_budget

    # Check notification recorded rejection reason
    conn = get_db_connection(TEST_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT message FROM notifications WHERE employee_id = 'EMP001' AND request_id = ?", (req_id,))
    notif = cursor.fetchone()
    assert notif is not None
    assert "REJECTED" in notif["message"]
    assert "Not an essential business expense" in notif["message"]
    conn.close()
