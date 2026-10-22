"""
FlowPilot LangGraph Workflow Engine
Orchestrates autonomous multi-step business workflows with human-in-the-loop approvals.
Supported Workflows:
1. Leave Request:    Employee -> Manager Approval -> HR Balance Check -> Notification
2. Purchase Request: Employee -> Manager Approval -> Finance Budget Check -> Notification
"""

import os
import json
import uuid
from datetime import datetime
from typing import TypedDict, Optional, Dict, Any, Literal

from langgraph.graph import StateGraph, END
from db.database import get_db_connection, log_audit, DB_PATH
from agent.llm import classify_and_extract_request
from agent.tools import (
    check_leave_balance,
    deduct_leave_balance,
    check_budget,
    deduct_budget,
    request_approval,
    send_notification
)


class WorkflowState(TypedDict):
    request_id: str
    employee_id: str
    department: str
    raw_text: str
    workflow_type: str                   # 'leave', 'purchase', or 'unknown'
    extracted_data: Dict[str, Any]
    status: str                          # 'draft', 'pending_approval', 'approved', 'rejected', 'completed', 'failed'
    current_step: str
    approval_id: Optional[int]
    approval_role: Optional[str]         # 'Manager', 'HR', 'Finance'
    approval_decision: Optional[str]     # 'PENDING', 'APPROVED', 'REJECTED'
    approval_comments: Optional[str]
    error_message: Optional[str]


def generate_request_id(prefix: str = "REQ") -> str:
    """Generates a human-friendly unique request ID."""
    today = datetime.now().strftime("%Y%m%d")
    short_uuid = uuid.uuid4().hex[:6].upper()
    return f"{prefix}-{today}-{short_uuid}"


# ==================== WORKFLOW NODES ====================

def classify_node(state: WorkflowState) -> WorkflowState:
    """
    Step 1: Analyzes plain English input using LLM and extracts structured data.
    """
    request_id = state.get("request_id") or generate_request_id()
    employee_id = state.get("employee_id", "EMP001")
    raw_text = state.get("raw_text", "")

    # Get employee's department from DB
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT department FROM employees WHERE id = ?", (employee_id,))
    emp_row = cursor.fetchone()
    department = emp_row["department"] if emp_row else "Engineering"
    conn.close()

    # Call LLM / Fallback classifier
    classification = classify_and_extract_request(
        user_text=raw_text,
        employee_department=department
    )

    workflow_type = classification.get("workflow_type", "unknown")
    extracted_data = classification.get("extracted_data", {})

    # Ensure purchase requests retain department context if omitted
    if workflow_type == "purchase" and "department" not in extracted_data:
        extracted_data["department"] = department

    # Save initial request record into DB
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT OR REPLACE INTO requests 
        (id, employee_id, workflow_type, raw_text, structured_data, current_step, status)
        VALUES (?, ?, ?, ?, ?, 'classified', 'draft')
        """,
        (request_id, employee_id, workflow_type, raw_text, json.dumps(extracted_data))
    )
    conn.commit()
    conn.close()

    log_audit(
        request_id=request_id,
        step_name="Classify Request",
        actor="Agent",
        action="CLASSIFY_INPUT",
        details={
            "workflow_type": workflow_type,
            "extracted_data": extracted_data,
            "summary": classification.get("summary", "")
        }
    )

    return {
        **state,
        "request_id": request_id,
        "department": department,
        "workflow_type": workflow_type,
        "extracted_data": extracted_data,
        "current_step": "classified",
        "status": "draft"
    }


def request_manager_approval_node(state: WorkflowState) -> WorkflowState:
    """
    Step 2: Registers Manager approval requirement and pauses the workflow.
    """
    request_id = state["request_id"]
    decision = state.get("approval_decision")

    # If decision is already made (e.g. resumed after approver action)
    if decision in ["APPROVED", "REJECTED"]:
        return state

    # Otherwise, create pending approval record and pause
    approval_result = request_approval(
        role="Manager",
        request_id=request_id
    )

    return {
        **state,
        "approval_id": approval_result.get("approval_id"),
        "approval_role": "Manager",
        "approval_decision": "PENDING",
        "current_step": "manager_approval",
        "status": "pending_approval"
    }


def check_hr_balance_node(state: WorkflowState) -> WorkflowState:
    """
    Step 3 (Leave): Verifies employee leave balance and deducts approved days.
    """
    request_id = state["request_id"]
    employee_id = state["employee_id"]
    extracted = state.get("extracted_data", {})
    requested_days = int(extracted.get("days", 1))
    leave_type = extracted.get("leave_type", "annual")

    balance_check = check_leave_balance(employee_id)
    if not balance_check.get("success"):
        error = balance_check.get("error", "Failed to retrieve leave balance.")
        log_audit(request_id, "Check HR Balance", "Agent", "BALANCE_CHECK_FAILED", {"error": error})
        return {
            **state,
            "current_step": "hr_balance_check",
            "status": "failed",
            "error_message": error
        }

    target_category = f"{leave_type}_leave" if not leave_type.endswith("_leave") else leave_type
    available = balance_check.get(target_category, balance_check.get("annual_leave", 0))

    if available < requested_days:
        error = f"Insufficient {leave_type} leave balance. Requested: {requested_days}, Available: {available}"
        log_audit(request_id, "Check HR Balance", "Agent", "INSUFFICIENT_BALANCE", {
            "requested": requested_days,
            "available": available,
            "leave_type": leave_type
        })
        return {
            **state,
            "current_step": "hr_balance_check",
            "status": "failed",
            "error_message": error
        }

    # Deduct balance
    deduct_res = deduct_leave_balance(employee_id, days=requested_days, leave_type=leave_type)
    log_audit(request_id, "Check HR Balance", "Agent", "BALANCE_DEDUCTED", deduct_res)

    return {
        **state,
        "current_step": "hr_balance_check",
        "status": "approved",
        "error_message": None
    }


def check_finance_budget_node(state: WorkflowState) -> WorkflowState:
    """
    Step 3 (Purchase): Verifies departmental budget and deducts purchase amount.
    """
    request_id = state["request_id"]
    extracted = state.get("extracted_data", {})
    department = extracted.get("department") or state.get("department", "Engineering")
    amount = float(extracted.get("amount", 0.0))
    item = extracted.get("item", "Equipment")

    budget_check = check_budget(department, amount)
    if not budget_check.get("success"):
        error = budget_check.get("error", f"Department '{department}' not found in budget database.")
        log_audit(request_id, "Check Finance Budget", "Agent", "BUDGET_CHECK_FAILED", {"error": error})
        return {
            **state,
            "current_step": "finance_budget_check",
            "status": "failed",
            "error_message": error
        }

    if not budget_check.get("has_budget"):
        remaining = budget_check.get("remaining_budget", 0.0)
        error = f"Insufficient budget for {department}. Requested: ${amount:,.2f}, Available: ${remaining:,.2f}"
        log_audit(request_id, "Check Finance Budget", "Agent", "INSUFFICIENT_BUDGET", {
            "department": department,
            "requested": amount,
            "remaining": remaining,
            "item": item
        })
        return {
            **state,
            "current_step": "finance_budget_check",
            "status": "failed",
            "error_message": error
        }

    # Deduct budget
    deduct_res = deduct_budget(department, amount)
    log_audit(request_id, "Check Finance Budget", "Agent", "BUDGET_DEDUCTED", deduct_res)

    return {
        **state,
        "current_step": "finance_budget_check",
        "status": "approved",
        "error_message": None
    }


def notify_node(state: WorkflowState) -> WorkflowState:
    """
    Step 4: Sends final notification to the employee and updates request status.
    """
    request_id = state["request_id"]
    employee_id = state["employee_id"]
    status = state.get("status", "completed")
    decision = state.get("approval_decision")
    error = state.get("error_message")
    extracted = state.get("extracted_data", {})
    wf_type = state.get("workflow_type", "request")

    if decision == "REJECTED":
        reason = state.get("approval_comments") or "Manager rejected the request."
        message = f"Your {wf_type} request ({request_id}) was REJECTED by Manager. Reason: {reason}"
        final_status = "rejected"
    elif status == "failed" or error:
        message = f"Your {wf_type} request ({request_id}) could not be completed. Reason: {error}"
        final_status = "failed"
    else:
        if wf_type == "leave":
            days = extracted.get("days", 1)
            leave_type = extracted.get("leave_type", "leave")
            message = f"Your {leave_type} leave request ({request_id}) for {days} day(s) has been APPROVED and confirmed by HR."
        elif wf_type == "purchase":
            item = extracted.get("item", "item")
            amount = float(extracted.get("amount", 0.0))
            dept = extracted.get("department", "Engineering")
            message = f"Your purchase request ({request_id}) for '{item}' (${amount:,.2f}) for {dept} has been APPROVED and confirmed by Finance."
        else:
            message = f"Your {wf_type} request ({request_id}) has been processed successfully."
        final_status = "completed"

    send_notification(employee_id, message, request_id=request_id)

    # Update request table to final status
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE requests SET status = ?, current_step = 'completed', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (final_status, request_id)
    )
    conn.commit()
    conn.close()

    log_audit(
        request_id=request_id,
        step_name="Notify Employee",
        actor="Agent",
        action="WORKFLOW_FINALIZED",
        details={"final_status": final_status, "message": message}
    )

    return {
        **state,
        "current_step": "completed",
        "status": final_status
    }


# ==================== CONDITIONAL ROUTERS ====================

def route_after_classification(state: WorkflowState) -> Literal["request_manager_approval", "notify_result"]:
    wf_type = state.get("workflow_type")
    if wf_type in ["leave", "purchase"]:
        return "request_manager_approval"
    return "notify_result"


def route_after_approval_request(
    state: WorkflowState
) -> Literal["check_hr_balance", "check_finance_budget", "notify_result", "__end__"]:
    decision = state.get("approval_decision")
    wf_type = state.get("workflow_type")

    if decision == "APPROVED":
        if wf_type == "purchase":
            return "check_finance_budget"
        return "check_hr_balance"
    elif decision == "REJECTED":
        return "notify_result"
    # When pending, pause graph execution (Human in the Loop)
    return END


# ==================== COMPILE GRAPH ====================

def build_workflow_graph():
    """Builds and compiles the FlowPilot StateGraph for Leave and Purchase workflows."""
    graph = StateGraph(WorkflowState)

    graph.add_node("classify", classify_node)
    graph.add_node("request_manager_approval", request_manager_approval_node)
    graph.add_node("check_hr_balance", check_hr_balance_node)
    graph.add_node("check_finance_budget", check_finance_budget_node)
    graph.add_node("notify_result", notify_node)

    graph.set_entry_point("classify")

    graph.add_conditional_edges(
        "classify",
        route_after_classification,
        {
            "request_manager_approval": "request_manager_approval",
            "notify_result": "notify_result"
        }
    )

    graph.add_conditional_edges(
        "request_manager_approval",
        route_after_approval_request,
        {
            "check_hr_balance": "check_hr_balance",
            "check_finance_budget": "check_finance_budget",
            "notify_result": "notify_result",
            END: END
        }
    )

    graph.add_edge("check_hr_balance", "notify_result")
    graph.add_edge("check_finance_budget", "notify_result")
    graph.add_edge("notify_result", END)

    return graph.compile()


flowpilot_graph = build_workflow_graph()


# ==================== EXECUTION HELPERS ====================

def run_workflow(raw_text: str, employee_id: str = "EMP001") -> WorkflowState:
    """
    Submits and executes any business workflow (leave or purchase) from plain English.
    Pauses execution when awaiting human approval.
    """
    initial_state: WorkflowState = {
        "request_id": "",
        "employee_id": employee_id,
        "department": "Engineering",
        "raw_text": raw_text,
        "workflow_type": "unknown",
        "extracted_data": {},
        "status": "draft",
        "current_step": "init",
        "approval_id": None,
        "approval_role": None,
        "approval_decision": None,
        "approval_comments": None,
        "error_message": None
    }
    return flowpilot_graph.invoke(initial_state)


def run_leave_workflow(raw_text: str, employee_id: str = "EMP001") -> WorkflowState:
    """Alias for backwards compatibility with Phase 2 leave requests."""
    return run_workflow(raw_text=raw_text, employee_id=employee_id)


def run_purchase_workflow(raw_text: str, employee_id: str = "EMP001") -> WorkflowState:
    """Submits and starts a purchase workflow."""
    return run_workflow(raw_text=raw_text, employee_id=employee_id)


def resume_workflow(
    request_id: str,
    decision: Literal["APPROVED", "REJECTED"],
    comments: str = "",
    approver_id: str = "EMP002"
) -> WorkflowState:
    """
    Resumes a paused workflow (leave or purchase) after an approver makes a decision.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM requests WHERE id = ?", (request_id,))
    req = cursor.fetchone()
    if not req:
        conn.close()
        raise ValueError(f"Request {request_id} not found.")

    # Update approvals table
    cursor.execute(
        """
        UPDATE approvals
        SET decision = ?, comments = ?, approver_id = ?, decided_at = CURRENT_TIMESTAMP
        WHERE request_id = ? AND decision = 'PENDING'
        """,
        (decision, comments, approver_id, request_id)
    )
    conn.commit()
    conn.close()

    log_audit(
        request_id=request_id,
        step_name="Human Approval Decision",
        actor="Manager",
        action=f"DECISION_{decision}",
        details={"decision": decision, "comments": comments, "approver_id": approver_id}
    )

    extracted_data = json.loads(req["structured_data"]) if req["structured_data"] else {}

    resumed_state: WorkflowState = {
        "request_id": request_id,
        "employee_id": req["employee_id"],
        "department": extracted_data.get("department", "Engineering"),
        "raw_text": req["raw_text"],
        "workflow_type": req["workflow_type"],
        "extracted_data": extracted_data,
        "status": "pending_approval",
        "current_step": "manager_approval",
        "approval_id": None,
        "approval_role": "Manager",
        "approval_decision": decision,
        "approval_comments": comments,
        "error_message": None
    }

    # Execute next step based on workflow type and approval decision
    if decision == "APPROVED":
        if req["workflow_type"] == "purchase":
            step_state = check_finance_budget_node(resumed_state)
        else:
            step_state = check_hr_balance_node(resumed_state)
        final_state = notify_node(step_state)
    else:
        final_state = notify_node(resumed_state)

    return final_state
