"""Authentication helpers and role-based navigation rules."""

from contextlib import closing
from typing import Optional

import bcrypt

from db.database import get_db_connection


PAGES_BY_ROLE = {
    "employee": ("👤 Employee Portal", "📜 Audit & Reasoning Trail"),
    "manager": ("🛡️ Approver Dashboard", "📜 Audit & Reasoning Trail"),
    "hr": ("🛡️ Approver Dashboard", "📜 Audit & Reasoning Trail"),
    "finance": ("🛡️ Approver Dashboard", "📜 Audit & Reasoning Trail"),
}


def authenticate_user(username: str, password: str) -> Optional[dict]:
    """Return a safe user session record when the supplied credentials match."""
    with closing(get_db_connection()) as conn:
        user = conn.execute(
            """
            SELECT id, username, password_hash, role, employee_id
            FROM users
            WHERE username = ?
            """,
            (username.strip(),),
        ).fetchone()

    if user is None:
        return None
    try:
        valid_password = bcrypt.checkpw(
            password.encode("utf-8"),
            user["password_hash"].encode("utf-8"),
        )
    except ValueError:
        return None
    if not valid_password:
        return None
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "employee_id": user["employee_id"],
    }


def pages_for_role(role: str) -> tuple[str, ...]:
    """Return only the pages available to a role."""
    return PAGES_BY_ROLE.get(role, ())


def has_page_access(role: str, page: str) -> bool:
    """Check whether a role may enter a page, including direct view calls."""
    return page in pages_for_role(role)
