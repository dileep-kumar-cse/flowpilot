"""
FlowPilot Tools Module
Implements business tools for leave balance checks, budget verification,
approval requests, and notifications using the SQLite database.
"""

from typing import Dict, Any, Optional
from db.database import get_db_connection, log_audit, DB_PATH


def check_leave_balance(employee_id: str, db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Checks the remaining leave balances (annual, sick, casual) for a given employee.

    Args:
        employee_id: The unique identifier of the employee (e.g. 'EMP001').
        db_path: Path to the SQLite database.

    Returns:
        Dict containing balance status and breakdown, or error information.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT b.employee_id, e.name, b.annual_leave, b.sick_leave, b.casual_leave
        FROM leave_balances b
        JOIN employees e ON b.employee_id = e.id
        WHERE b.employee_id = ?
        """,
        (employee_id,)
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {
            "success": False,
            "error": f"No leave balance record found for employee '{employee_id}'"
        }

    total_available = row["annual_leave"] + row["sick_leave"] + row["casual_leave"]
    return {
        "success": True,
        "employee_id": row["employee_id"],
        "employee_name": row["name"],
        "annual_leave": row["annual_leave"],
        "sick_leave": row["sick_leave"],
        "casual_leave": row["casual_leave"],
        "total_available": total_available
    }


def deduct_leave_balance(
    employee_id: str,
    days: int,
    leave_type: str = "annual",
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Deducts approved leave days from the specified balance category.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    
    col_map = {
        "annual": "annual_leave",
        "sick": "sick_leave",
        "casual": "casual_leave"
    }
    target_col = col_map.get(leave_type.lower(), "annual_leave")

    cursor.execute(f"SELECT {target_col} FROM leave_balances WHERE employee_id = ?", (employee_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"success": False, "error": f"Employee {employee_id} not found."}

    current_val = row[0]
    if current_val < days:
        conn.close()
        return {
            "success": False,
            "error": f"Insufficient {target_col}: requested {days}, available {current_val}"
        }

    new_val = current_val - days
    cursor.execute(
        f"UPDATE leave_balances SET {target_col} = ?, updated_at = CURRENT_TIMESTAMP WHERE employee_id = ?",
        (new_val, employee_id)
    )
    conn.commit()
    conn.close()

    return {
        "success": True,
        "employee_id": employee_id,
        "leave_type": target_col,
        "deducted_days": days,
        "remaining": new_val
    }


def check_budget(department: str, amount: float, db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Checks if a department has sufficient remaining budget for a purchase request.

    Args:
        department: Department name (e.g. 'Engineering', 'Marketing').
        amount: Requested purchase amount in USD.
        db_path: Path to the SQLite database.

    Returns:
        Dict indicating whether sufficient budget exists along with budget figures.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT department, total_budget, spent_budget, remaining_budget
        FROM budgets
        WHERE LOWER(department) = LOWER(?)
        """,
        (department,)
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {
            "success": False,
            "has_budget": False,
            "error": f"Department '{department}' not found in budget records."
        }

    remaining = row["remaining_budget"]
    has_budget = remaining >= amount

    return {
        "success": True,
        "department": row["department"],
        "requested_amount": amount,
        "total_budget": row["total_budget"],
        "spent_budget": row["spent_budget"],
        "remaining_budget": remaining,
        "has_budget": has_budget
    }


def deduct_budget(department: str, amount: float, db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Deducts approved purchase amount from the department's budget.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT spent_budget, remaining_budget FROM budgets WHERE LOWER(department) = LOWER(?)",
        (department,)
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"success": False, "error": f"Department {department} not found."}

    spent, remaining = row["spent_budget"], row["remaining_budget"]
    if remaining < amount:
        conn.close()
        return {"success": False, "error": "Insufficient budget."}

    new_spent = spent + amount
    new_remaining = remaining - amount
    cursor.execute(
        "UPDATE budgets SET spent_budget = ?, remaining_budget = ? WHERE LOWER(department) = LOWER(?)",
        (new_spent, new_remaining, department)
    )
    conn.commit()
    conn.close()

    return {
        "success": True,
        "department": department,
        "deducted": amount,
        "new_remaining": new_remaining
    }


def request_approval(
    role: str,
    request_id: str,
    approver_id: Optional[str] = None,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Registers a human-in-the-loop approval requirement for a request and pauses the workflow.

    Args:
        role: The role required to approve ('Manager', 'HR', 'Finance').
        request_id: The workflow request ID (e.g. 'REQ-101').
        approver_id: Optional specific employee ID of the approver.
        db_path: Path to the SQLite database.

    Returns:
        Dict confirming creation of the pending approval record.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Create pending approval entry
    cursor.execute(
        """
        INSERT INTO approvals (request_id, approver_role, approver_id, decision)
        VALUES (?, ?, ?, 'PENDING')
        """,
        (request_id, role, approver_id)
    )
    approval_id = cursor.lastrowid

    # Update request status to pending_approval
    cursor.execute(
        """
        UPDATE requests
        SET status = 'pending_approval', current_step = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (f"{role.lower()}_approval", request_id)
    )
    conn.commit()
    conn.close()

    # Log audit event
    log_audit(
        request_id=request_id,
        step_name=f"Request Approval ({role})",
        actor="Agent",
        action="REQUEST_APPROVAL",
        details={"approval_id": approval_id, "role": role, "status": "PENDING"},
        db_path=db_path
    )

    return {
        "success": True,
        "approval_id": approval_id,
        "request_id": request_id,
        "approver_role": role,
        "decision": "PENDING",
        "message": f"Approval requested from {role}. Workflow paused awaiting human action."
    }


def send_notification(
    employee_id: str,
    message: str,
    request_id: Optional[str] = None,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Simulates sending an employee notification by writing an entry to the notifications table.

    Args:
        employee_id: Target employee ID to notify.
        message: Notification message text.
        request_id: Optional related request ID.
        db_path: Path to the SQLite database.

    Returns:
        Dict confirming notification creation.
    """
    conn = get_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO notifications (employee_id, request_id, message)
        VALUES (?, ?, ?)
        """,
        (employee_id, request_id, message)
    )
    notif_id = cursor.lastrowid
    conn.commit()
    conn.close()

    if request_id:
        log_audit(
            request_id=request_id,
            step_name="Send Notification",
            actor="Agent",
            action="SEND_NOTIFICATION",
            details={"notification_id": notif_id, "employee_id": employee_id, "message": message},
            db_path=db_path
        )

    return {
        "success": True,
        "notification_id": notif_id,
        "employee_id": employee_id,
        "message": message
    }
