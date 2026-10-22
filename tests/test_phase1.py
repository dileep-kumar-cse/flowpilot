"""
Tests for Phase 1: Database, Seed Data, and Mock Tools.
"""

import os
import pytest
import sqlite3
from db.database import init_db, get_db_connection, log_audit
from db.seed import seed_database
from agent.tools import (
    check_leave_balance,
    deduct_leave_balance,
    check_budget,
    deduct_budget,
    request_approval,
    send_notification
)

TEST_DB = "test_flowpilot.db"


@pytest.fixture(autouse=True)
def setup_test_db():
    """Setup and teardown a clean test SQLite database."""
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    seed_database(TEST_DB)
    yield
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


def test_seed_data_presence():
    """Verify that employees, balances, and budgets are seeded."""
    conn = get_db_connection(TEST_DB)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM employees")
    emp_count = cursor.fetchone()[0]
    assert emp_count >= 5

    cursor.execute("SELECT COUNT(*) FROM leave_balances")
    leave_count = cursor.fetchone()[0]
    assert leave_count >= 5

    cursor.execute("SELECT COUNT(*) FROM budgets")
    budget_count = cursor.fetchone()[0]
    assert budget_count >= 4

    conn.close()


def test_check_leave_balance_success():
    """Verify check_leave_balance returns correct balance for EMP001."""
    res = check_leave_balance("EMP001", db_path=TEST_DB)
    assert res["success"] is True
    assert res["employee_id"] == "EMP001"
    assert res["annual_leave"] == 12
    assert res["total_available"] == 24


def test_check_leave_balance_not_found():
    """Verify check_leave_balance handles invalid employee ID."""
    res = check_leave_balance("EMP999", db_path=TEST_DB)
    assert res["success"] is False
    assert "not found" in res["error"].lower() or "no leave balance" in res["error"].lower()


def test_deduct_leave_balance():
    """Verify deducting leave days updates balance accurately."""
    res = deduct_leave_balance("EMP001", days=3, leave_type="annual", db_path=TEST_DB)
    assert res["success"] is True
    assert res["remaining"] == 9

    # Check updated in DB
    balance = check_leave_balance("EMP001", db_path=TEST_DB)
    assert balance["annual_leave"] == 9


def test_check_budget():
    """Verify check_budget accurately validates available departmental funds."""
    # Engineering budget has remaining 38000
    res_ok = check_budget("Engineering", 1500.0, db_path=TEST_DB)
    assert res_ok["success"] is True
    assert res_ok["has_budget"] is True

    # Check excessive amount
    res_exceeded = check_budget("Engineering", 100000.0, db_path=TEST_DB)
    assert res_exceeded["success"] is True
    assert res_exceeded["has_budget"] is False


def test_deduct_budget():
    """Verify deducting budget adjusts remaining funds."""
    res = deduct_budget("Engineering", 2000.0, db_path=TEST_DB)
    assert res["success"] is True
    assert res["new_remaining"] == 36000.0


def test_request_approval_and_notification():
    """Verify request_approval creates pending approval and notification writes entry."""
    # First create a mock request entry
    conn = get_db_connection(TEST_DB)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO requests (id, employee_id, workflow_type, raw_text, structured_data, current_step, status)
        VALUES ('REQ-TEST-1', 'EMP001', 'leave', '3 days leave', '{}', 'init', 'draft')
        """
    )
    conn.commit()
    conn.close()

    # Request approval
    appr_res = request_approval(role="Manager", request_id="REQ-TEST-1", db_path=TEST_DB)
    assert appr_res["success"] is True
    assert appr_res["decision"] == "PENDING"

    # Send notification
    notif_res = send_notification("EMP001", "Your leave request is submitted", request_id="REQ-TEST-1", db_path=TEST_DB)
    assert notif_res["success"] is True

    # Verify audit log recorded events
    conn = get_db_connection(TEST_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM audit_log WHERE request_id = 'REQ-TEST-1'")
    audit_count = cursor.fetchone()[0]
    assert audit_count >= 2
    conn.close()
