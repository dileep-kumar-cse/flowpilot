"""Authentication and role-scoped workflow tests."""

import os
from contextlib import closing
from pathlib import Path

import pytest

from agent.graph import resume_workflow, run_workflow
from db.database import get_db_connection
from db.seed import seed_database
from ui.auth import authenticate_user, has_page_access
from streamlit.testing.v1 import AppTest


TEST_DB = "test_flowpilot_auth.db"


@pytest.fixture(autouse=True)
def setup_auth_test_db(monkeypatch):
    monkeypatch.setenv("FLOWPILOT_DB_PATH", TEST_DB)
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    seed_database(TEST_DB)
    yield
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


def test_demo_login_authenticates_without_returning_password_hash():
    user = authenticate_user("employee", "employee123")

    assert user == {
        "id": "USR001",
        "username": "employee",
        "role": "employee",
        "employee_id": "EMP001",
    }
    assert authenticate_user("employee", "wrong-password") is None
    assert authenticate_user("missing-user", "employee123") is None


def test_employee_cannot_access_approver_page():
    assert not has_page_access("employee", "🛡️ Approver Dashboard")
    assert has_page_access("employee", "👤 Employee Portal")
    assert has_page_access("employee", "📜 Audit & Reasoning Trail")

    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run(timeout=30)
    app.text_input[0].set_value("employee")
    app.text_input[1].set_value("employee123")
    app.button[0].click()
    app.run(timeout=30)

    available_pages = app.radio[0].options
    assert not any("Approver Dashboard" in page for page in available_pages)
    assert any("Employee Portal" in page for page in available_pages)


def test_employee_request_is_approved_by_manager_username():
    employee = authenticate_user("employee", "employee123")
    manager = authenticate_user("manager", "manager123")
    state = run_workflow(
        raw_text="I need 2 days annual leave from Nov 5",
        employee_id=employee["employee_id"],
    )
    assert state["status"] == "pending_approval"

    result = resume_workflow(
        request_id=state["request_id"],
        decision="APPROVED",
        comments="Approved for the team.",
        approver_id=manager["employee_id"],
        approver_username=manager["username"],
    )
    assert result["status"] == "completed"

    with closing(get_db_connection(TEST_DB)) as conn:
        approval = conn.execute(
            """
            SELECT approver_role, approver_id, approver_username, decision
            FROM approvals
            WHERE request_id = ?
            """,
            (state["request_id"],),
        ).fetchone()
        audit_actors = conn.execute(
            """
            SELECT actor FROM audit_log
            WHERE request_id = ? AND action = 'DECISION_APPROVED'
            """,
            (state["request_id"],),
        ).fetchall()

    assert approval["approver_role"] == "Manager"
    assert approval["approver_id"] == manager["employee_id"]
    assert approval["approver_username"] == manager["username"]
    assert [row["actor"] for row in audit_actors] == ["manager"]
