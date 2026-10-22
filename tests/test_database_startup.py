from contextlib import closing

from db.database import get_db_connection
from db.seed import ensure_database


def test_missing_database_is_created_and_seeded(tmp_path):
    db_path = tmp_path / "new_flowpilot.db"

    ensure_database(str(db_path))

    assert db_path.is_file()
    with closing(get_db_connection(str(db_path))) as conn:
        assert conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 5
        assert conn.execute("SELECT COUNT(*) FROM budgets").fetchone()[0] == 4


def test_existing_database_is_not_reseeded(tmp_path):
    db_path = tmp_path / "existing_flowpilot.db"
    ensure_database(str(db_path))

    with closing(get_db_connection(str(db_path))) as conn:
        conn.execute("UPDATE employees SET name = 'Local User' WHERE id = 'EMP001'")
        conn.commit()

    ensure_database(str(db_path))

    with closing(get_db_connection(str(db_path))) as conn:
        name = conn.execute(
            "SELECT name FROM employees WHERE id = 'EMP001'"
        ).fetchone()[0]
    assert name == "Local User"
