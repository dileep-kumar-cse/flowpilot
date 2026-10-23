"""
FlowPilot Database Seeder
Populates initial sample data for employees, leave balances, and departmental budgets.
"""

import os
from typing import Optional

import bcrypt

from db.database import get_db_connection, init_db, DB_PATH


DEMO_USERS = (
    ("USR001", "employee", "employee123", "employee", "EMP001"),
    ("USR002", "manager", "manager123", "manager", "EMP002"),
    ("USR003", "hr", "hr123", "hr", "EMP003"),
    ("USR004", "finance", "finance123", "finance", "EMP004"),
)


def seed_demo_users(db_path: Optional[str] = None) -> None:
    """Create missing demo login accounts without replacing existing credentials."""
    conn = get_db_connection(db_path)
    existing_usernames = {
        row["username"]
        for row in conn.execute("SELECT username FROM users").fetchall()
    }
    missing_users = [
        (user_id, username, password, role, employee_id)
        for user_id, username, password, role, employee_id in DEMO_USERS
        if username not in existing_usernames
    ]
    conn.executemany(
        """
        INSERT OR IGNORE INTO users (id, username, password_hash, role, employee_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                user_id,
                username,
                bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
                role,
                employee_id,
            )
            for user_id, username, password, role, employee_id in missing_users
        ],
    )
    conn.commit()
    conn.close()


def ensure_database(db_path: Optional[str] = None) -> None:
    """Initialize the database and seed sample data when the file is missing."""
    target_path = db_path or os.environ.get("FLOWPILOT_DB_PATH") or DB_PATH
    if os.path.exists(target_path):
        init_db(target_path)
        seed_demo_users(target_path)
    else:
        seed_database(target_path)


def seed_database(db_path: str = DB_PATH) -> None:
    """Initializes tables and seeds initial test data."""
    init_db(db_path)
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Seed Employees (ordered so managers exist before direct reports)
    employees = [
        ("EMP004", "David Brown", "david@company.com", "Finance", "Finance", None),
        ("EMP002", "Bob Jones", "bob@company.com", "Engineering", "Manager", "EMP004"),
        ("EMP003", "Carol White", "carol@company.com", "HR", "HR", "EMP004"),
        ("EMP001", "Alice Smith", "alice@company.com", "Engineering", "Employee", "EMP002"),
        ("EMP005", "Eve Wilson", "eve@company.com", "Marketing", "Employee", "EMP002"),
    ]

    cursor.executemany("""
    INSERT INTO employees (id, name, email, department, role, manager_id)
    VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        name = excluded.name,
        email = excluded.email,
        department = excluded.department,
        role = excluded.role,
        manager_id = excluded.manager_id
    """, employees)

    # Seed Leave Balances
    leave_balances = [
        ("EMP001", 12, 8, 4),
        ("EMP002", 15, 10, 5),
        ("EMP003", 14, 10, 5),
        ("EMP004", 18, 10, 5),
        ("EMP005", 5, 3, 1),
    ]

    cursor.executemany("""
    INSERT OR REPLACE INTO leave_balances (employee_id, annual_leave, sick_leave, casual_leave)
    VALUES (?, ?, ?, ?)
    """, leave_balances)

    # Seed Department Budgets
    budgets = [
        ("Engineering", 50000.0, 12000.0, 38000.0),
        ("Marketing", 20000.0, 18500.0, 1500.0),
        ("HR", 15000.0, 3000.0, 12000.0),
        ("Finance", 25000.0, 5000.0, 20000.0),
    ]

    cursor.executemany("""
    INSERT OR REPLACE INTO budgets (department, total_budget, spent_budget, remaining_budget)
    VALUES (?, ?, ?, ?)
    """, budgets)

    conn.commit()
    conn.close()
    seed_demo_users(db_path)
    print("Database seeded successfully with sample employees, leave balances, and budgets.")


if __name__ == "__main__":
    seed_database()
