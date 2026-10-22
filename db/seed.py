"""
FlowPilot Database Seeder
Populates initial sample data for employees, leave balances, and departmental budgets.
"""

from db.database import get_db_connection, init_db, DB_PATH


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
    INSERT OR REPLACE INTO employees (id, name, email, department, role, manager_id)
    VALUES (?, ?, ?, ?, ?, ?)
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
    print("Database seeded successfully with sample employees, leave balances, and budgets.")


if __name__ == "__main__":
    seed_database()
