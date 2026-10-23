"""
FlowPilot Approver Dashboard
Review pending requests and resume their workflows with an approval decision.
"""

import json
from contextlib import closing

import streamlit as st

from agent.graph import resume_workflow
from db.database import get_db_connection
from ui.auth import has_page_access
from ui.styles import render_request_timeline, render_status_badge


def render_approver_view():
    user = st.session_state.get("user")
    if not user or not has_page_access(user.get("role", ""), "🛡️ Approver Dashboard"):
        st.error("The Approver Dashboard is available to approver accounts only.")
        return

    role = user["role"]
    if role == "manager":
        st.markdown("### Approver Dashboard")
        st.caption("Review requests assigned to the Manager role.")
    else:
        st.markdown(f"### {role.upper()} Check Queue")
        st.caption(f"Requests waiting on the {role.upper()} check.")

    with closing(get_db_connection()) as conn:
        if role == "manager":
            counts = conn.execute(
                """
                SELECT
                    SUM(CASE WHEN a.decision = 'PENDING' THEN 1 ELSE 0 END) AS pending,
                    SUM(CASE WHEN a.decision = 'APPROVED' THEN 1 ELSE 0 END) AS approved,
                    SUM(CASE WHEN a.decision = 'REJECTED' THEN 1 ELSE 0 END) AS rejected
                FROM approvals a
                WHERE a.approver_role = ?
                """,
                ("Manager",),
            ).fetchone()
            pending_items = conn.execute(
                """
                SELECT
                    a.request_id,
                    a.approver_role,
                    a.created_at AS requested_at,
                    r.workflow_type,
                    r.raw_text,
                    r.structured_data,
                    e.name AS employee_name,
                    e.department AS employee_dept
                FROM approvals a
                JOIN requests r ON a.request_id = r.id
                JOIN employees e ON r.employee_id = e.id
                WHERE a.decision = 'PENDING' AND a.approver_role = ?
                ORDER BY a.created_at ASC
                """,
                ("Manager",),
            ).fetchall()
            history = conn.execute(
                """
                SELECT a.request_id, a.decision, a.comments, a.decided_at,
                       COALESCE(a.approver_username, e.name) AS approver_name
                FROM approvals a
                LEFT JOIN employees e ON a.approver_id = e.id
                WHERE a.decision != 'PENDING' AND a.approver_role = ?
                ORDER BY a.decided_at DESC
                LIMIT 10
                """,
                ("Manager",),
            ).fetchall()
            waiting_items = []
        else:
            check_step = "hr_balance_check" if role == "hr" else "finance_budget_check"
            workflow_type = "leave" if role == "hr" else "purchase"
            waiting_items = conn.execute(
                """
                SELECT r.id, r.workflow_type, r.raw_text, r.current_step,
                       r.created_at, e.name AS employee_name, e.department
                FROM requests r
                JOIN employees e ON r.employee_id = e.id
                WHERE r.current_step = ? AND r.workflow_type = ?
                  AND r.status NOT IN ('completed', 'rejected', 'failed')
                ORDER BY r.created_at ASC
                """,
                (check_step, workflow_type),
            ).fetchall()
            pending_items = []

    if role != "manager":
        if not waiting_items:
            st.info(f"No requests are currently waiting on the {role.upper()} check.")
        else:
            for item in waiting_items:
                with st.container(border=True):
                    st.markdown(f"**{item['employee_name']}** · {item['department']}")
                    st.caption(
                        f"{item['workflow_type'].title()} · Request {item['id']} · "
                        f"Waiting since {item['created_at']}"
                    )
                    st.write(item["raw_text"])
        return

    metric_columns = st.columns(3)
    metric_columns[0].metric("Pending", counts["pending"] or 0)
    metric_columns[1].metric("Approved", counts["approved"] or 0)
    metric_columns[2].metric("Rejected", counts["rejected"] or 0)

    st.markdown("#### Requests awaiting review")
    if not pending_items:
        st.success("All caught up. There are no pending Manager approvals.")
    else:
        for item in pending_items:
            request_id = item["request_id"]
            workflow_type = item["workflow_type"]
            data = json.loads(item["structured_data"]) if item["structured_data"] else {}

            with st.container(border=True):
                st.markdown(f"**{item['employee_name']}** · {item['employee_dept']}")
                render_status_badge("pending_approval")
                st.caption(
                    f"{workflow_type.title()} · Request {request_id} · "
                    f"Awaiting {item['approver_role']} since {item['requested_at']}"
                )
                render_request_timeline(workflow_type, "pending_approval", "manager_approval")
                st.write(item["raw_text"])
                if workflow_type == "leave":
                    st.write(
                        f"**Leave details:** {data.get('days', 1)} days · "
                        f"{data.get('leave_type', 'annual')} · "
                        f"Starting {data.get('start_date', 'N/A')}"
                    )
                elif workflow_type == "purchase":
                    amount = float(data.get("amount", 0.0))
                    st.write(
                        f"**Purchase details:** {data.get('item', 'Item')} · "
                        f"${amount:,.2f} · {data.get('department', item['employee_dept'])}"
                    )

                comment = st.text_input(
                    "Comment (optional)",
                    key=f"comment_{request_id}",
                    placeholder="Add a note for the requester",
                )
                approve_column, reject_column = st.columns(2)
                if approve_column.button(
                    "Approve",
                    key=f"approve_{request_id}",
                    type="primary",
                    use_container_width=True,
                ):
                    with st.spinner("FlowPilot is processing..."):
                        final_state = resume_workflow(
                            request_id=request_id,
                            decision="APPROVED",
                            comments=comment.strip() or "Approved by manager",
                            approver_id=user["employee_id"],
                            approver_username=user["username"],
                        )
                    st.toast(f"Request {request_id} approved.")
                    if final_state["status"] == "completed":
                        st.success(f"Request {request_id} approved and completed.")
                        st.balloons()
                    else:
                        st.error(
                            f"Request {request_id} could not be completed: "
                            f"{final_state.get('error_message') or final_state['status']}."
                        )
                    st.rerun()

                if reject_column.button(
                    "Reject",
                    key=f"reject_{request_id}",
                    use_container_width=True,
                ):
                    with st.spinner("FlowPilot is processing..."):
                        final_state = resume_workflow(
                            request_id=request_id,
                            decision="REJECTED",
                            comments=comment.strip() or "Rejected by manager",
                            approver_id=user["employee_id"],
                            approver_username=user["username"],
                        )
                    st.toast(f"Request {request_id} rejected.")
                    st.error(f"Request {request_id} rejected.")
                    st.rerun()

    with st.expander("Recent approval history"):
        if not history:
            st.info("No approval decisions have been recorded yet.")
        else:
            for decision in history:
                badge = "🟢 Approved" if decision["decision"] == "APPROVED" else "🔴 Rejected"
                st.write(
                    f"**{decision['request_id']}** · {badge} by "
                    f"{decision['approver_name'] or 'Approver'} on {decision['decided_at']}"
                )
                if decision["comments"]:
                    st.caption(decision["comments"])
