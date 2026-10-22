"""
FlowPilot Approver Dashboard
Review pending requests and resume their workflows with an approval decision.
"""

import json
from contextlib import closing

import streamlit as st

from agent.graph import resume_workflow
from db.database import get_db_connection


def render_approver_view():
    st.markdown("### Approver Dashboard")
    st.caption("Review pending requests and record an approval decision.")

    with closing(get_db_connection()) as conn:
        approvers = conn.execute(
            """
            SELECT id, name, department, role
            FROM employees
            WHERE role IN ('Manager', 'HR', 'Finance')
            ORDER BY id ASC
            """
        ).fetchall()
        counts = conn.execute(
            """
            SELECT
                SUM(CASE WHEN status = 'pending_approval' THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN status IN ('approved', 'completed') THEN 1 ELSE 0 END) AS approved,
                SUM(CASE WHEN status IN ('rejected', 'failed') THEN 1 ELSE 0 END) AS rejected
            FROM requests
            """
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
            WHERE a.decision = 'PENDING'
            ORDER BY a.created_at ASC
            """
        ).fetchall()
        history = conn.execute(
            """
            SELECT a.request_id, a.decision, a.comments, a.decided_at,
                   e.name AS approver_name
            FROM approvals a
            LEFT JOIN employees e ON a.approver_id = e.id
            WHERE a.decision != 'PENDING'
            ORDER BY a.decided_at DESC
            LIMIT 10
            """
        ).fetchall()

    metric_columns = st.columns(3)
    metric_columns[0].metric("Pending", counts["pending"] or 0)
    metric_columns[1].metric("Approved", counts["approved"] or 0)
    metric_columns[2].metric("Rejected", counts["rejected"] or 0)

    approver_options = {
        f"{approver['name']} ({approver['role']} - {approver['department']})": approver["id"]
        for approver in approvers
    }
    if not approver_options:
        st.warning("No approver profiles are available.")
        return

    selected_label = st.selectbox("Active approver", list(approver_options))
    selected_approver_id = approver_options[selected_label]

    st.markdown("#### Requests awaiting review")
    if not pending_items:
        st.success("All caught up. There are no pending approvals.")
    else:
        for item in pending_items:
            request_id = item["request_id"]
            workflow_type = item["workflow_type"]
            data = json.loads(item["structured_data"]) if item["structured_data"] else {}

            with st.container(border=True):
                st.markdown(f"**{item['employee_name']}** · {item['employee_dept']}")
                st.caption(
                    f"{workflow_type.title()} · Request {request_id} · "
                    f"Awaiting {item['approver_role']} since {item['requested_at']}"
                )
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
                    with st.spinner("Processing approval..."):
                        final_state = resume_workflow(
                            request_id=request_id,
                            decision="APPROVED",
                            comments=comment.strip() or "Approved by manager",
                            approver_id=selected_approver_id,
                        )
                    st.success(
                        f"Request {request_id} processed with status "
                        f"{final_state['status']}."
                    )
                    st.rerun()

                if reject_column.button(
                    "Reject",
                    key=f"reject_{request_id}",
                    use_container_width=True,
                ):
                    with st.spinner("Processing rejection..."):
                        final_state = resume_workflow(
                            request_id=request_id,
                            decision="REJECTED",
                            comments=comment.strip() or "Rejected by manager",
                            approver_id=selected_approver_id,
                        )
                    st.error(
                        f"Request {request_id} processed with status "
                        f"{final_state['status']}."
                    )
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
