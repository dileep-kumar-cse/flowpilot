"""
FlowPilot LangGraph Workflow Engine
Orchestrates autonomous multi-step business workflows with human-in-the-loop approvals.
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
    Step 3: Verifies employee leave balance and deducts approved days.
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

    if decision == "REJECTED":
        reason = state.get("approval_comments") or "Manager rejected the request."
        message = f"Your {state.get('workflow_type', 'workflow')} request ({request_id}) was REJECTED. Reason: {reason}"
        final_status = "rejected"
    elif status == "failed" or error:
        message = f"Your {state.get('workflow_type', 'workflow')} request ({request_id}) could not be completed. Reason: {error}"
        final_status = "failed"
    else:
        days = extracted.get("days", 1)
        leave_type = extracted.get("leave_type", "leave")
        message = f"Your {leave_type} leave request ({request_id}) for {days} day(s) has been APPROVED and confirmed by HR."
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
    if wf_type == "leave":
        return "request_manager_approval"
    # Unknown or unsupported types route to notify error
    return "notify_result"


def route_after_approval_request(state: WorkflowState) -> Literal["check_hr_balance", "notify_result", "__end__"]:
    decision = state.get("approval_decision")
    if decision == "APPROVED":
        return "check_hr_balance"
    elif decision == "REJECTED":
        return "notify_result"
    # When pending, pause graph execution (Human in the Loop)
    return END


# ==================== COMPILE GRAPH ====================

def build_workflow_graph():
    """Builds and compiles the FlowPilot StateGraph."""
    graph = StateGraph(WorkflowState)

    graph.add_node("classify", classify_node)
    graph.add_node("request_manager_approval", request_manager_approval_node)
    graph.add_node("check_hr_balance", check_hr_balance_node)
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
            "notify_result": "notify_result",
            END: END
        }
    )

    graph.add_edge("check_hr_balance", "notify_result")
    graph.add_edge("notify_result", END)

    return graph.compile()


flowpilot_graph = build_workflow_graph()


# ==================== EXECUTION HELPERS ====================

def run_leave_workflow(raw_text: str, employee_id: str = "EMP001") -> WorkflowState:
    """
    Submits and starts a leave workflow from plain English text.
    Pauses when awaiting human approval.
    """
    initial_state: WorkflowState = {
        "request_id": "",
        "employee_id": employee_id,
        "department": "Engineering",
        "raw_text": raw_text,
        "workflow_type": "leave",
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


def resume_workflow(
    request_id: str,
    decision: Literal["APPROVED", "REJECTED"],
    comments: str = "",
    approver_id: str = "EMP002"
) -> WorkflowState:
    """
    Resumes a paused workflow after an approver makes a decision.
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
        "department": "Engineering",
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

    # Execute directly from check_hr_balance if approved, or notify_result if rejected
    if decision == "APPROVED":
        step_state = check_hr_balance_node(resumed_state)
        final_state = notify_node(step_state)
    else:
        final_state = notify_node(resumed_state)

    return final_state
