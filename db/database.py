"""
FlowPilot Database Module
Handles SQLite schema definition, connection management, and audit logging.
"""

import os
import sqlite3
import json
from datetime import datetime
from typing import Optional, Dict, Any, List

DB_PATH = os.environ.get("FLOWPILOT_DB_PATH", "flowpilot.db")


def get_db_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Returns a SQLite connection with Row factory enabled."""
    target_path = db_path or os.environ.get("FLOWPILOT_DB_PATH") or DB_PATH
    conn = sqlite3.connect(target_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    """Initializes all necessary tables for FlowPilot."""
    target_path = db_path or os.environ.get("FLOWPILOT_DB_PATH") or DB_PATH
    conn = get_db_connection(target_path)
    cursor = conn.cursor()

    # 1. Employees table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS employees (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        department TEXT NOT NULL,
        role TEXT NOT NULL,          -- 'Employee', 'Manager', 'HR', 'Finance'
        manager_id TEXT,
        FOREIGN KEY (manager_id) REFERENCES employees (id)
    );
    """)

    # 2. Leave balances table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS leave_balances (
        employee_id TEXT PRIMARY KEY,
        annual_leave INTEGER NOT NULL DEFAULT 15,
        sick_leave INTEGER NOT NULL DEFAULT 10,
        casual_leave INTEGER NOT NULL DEFAULT 5,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (employee_id) REFERENCES employees (id)
    );
    """)

    # 3. Budgets table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS budgets (
        department TEXT PRIMARY KEY,
        total_budget REAL NOT NULL,
        spent_budget REAL NOT NULL DEFAULT 0.0,
        remaining_budget REAL NOT NULL
    );
    """)

    # 4. Requests table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS requests (
        id TEXT PRIMARY KEY,
        employee_id TEXT NOT NULL,
        workflow_type TEXT NOT NULL,     -- 'leave' or 'purchase'
        raw_text TEXT NOT NULL,
        structured_data TEXT NOT NULL,   -- JSON representation of extracted fields
        current_step TEXT NOT NULL,
        status TEXT NOT NULL,            -- 'pending_approval', 'approved', 'rejected', 'completed', 'failed'
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (employee_id) REFERENCES employees (id)
    );
    """)

    # 5. Approvals table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS approvals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id TEXT NOT NULL,
        approver_role TEXT NOT NULL,     -- 'Manager', 'HR', 'Finance'
        approver_id TEXT,
        decision TEXT NOT NULL DEFAULT 'PENDING',  -- 'PENDING', 'APPROVED', 'REJECTED'
        comments TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        decided_at TIMESTAMP,
        FOREIGN KEY (request_id) REFERENCES requests (id)
    );
    """)

    # 6. Audit log table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id TEXT NOT NULL,
        step_name TEXT NOT NULL,
        actor TEXT NOT NULL,             -- 'Employee', 'Agent', 'Manager', 'HR', 'Finance', 'System'
        action TEXT NOT NULL,
        details TEXT,                    -- JSON or string describing action/payload
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 7. Notifications table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id TEXT NOT NULL,
        request_id TEXT,
        message TEXT NOT NULL,
        is_read INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (employee_id) REFERENCES employees (id)
    );
    """)

    conn.commit()
    conn.close()


def log_audit(
    request_id: str,
    step_name: str,
    actor: str,
    action: str,
    details: Optional[Any] = None,
    db_path: Optional[str] = None
) -> None:
    """Records an audit event into the audit_log table."""
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    details_str = json.dumps(details) if isinstance(details, (dict, list)) else (str(details) if details is not None else "")
    cursor.execute(
        """
        INSERT INTO audit_log (request_id, step_name, actor, action, details)
        VALUES (?, ?, ?, ?, ?)
        """,
        (request_id, step_name, actor, action, details_str)
    )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
