"""
FlowPilot audit trail, request analytics, and company status overview.
"""

import json
from contextlib import closing

import streamlit as st

from db.database import get_db_connection


def render_audit_view():
    st.markdown("### Audit & Reasoning Trail")
    st.caption("Review workflow events, their timestamps, and request activity.")

    with closing(get_db_connection()) as conn:
        total_requests = conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
        pending_requests = conn.execute(
            "SELECT COUNT(*) FROM requests WHERE status = 'pending_approval'"
        ).fetchone()[0]
        completed_requests = conn.execute(
            "SELECT COUNT(*) FROM requests WHERE status = 'completed'"
        ).fetchone()[0]
        unsuccessful_requests = conn.execute(
            "SELECT COUNT(*) FROM requests WHERE status IN ('rejected', 'failed')"
        ).fetchone()[0]
        request_ids = [
            row[0]
            for row in conn.execute(
                "SELECT id FROM requests ORDER BY created_at DESC"
            ).fetchall()
        ]
        requests_by_type = conn.execute(
            "SELECT workflow_type, COUNT(*) AS count FROM requests GROUP BY workflow_type"
        ).fetchall()
        requests_by_status = conn.execute(
            "SELECT status, COUNT(*) AS count FROM requests GROUP BY status"
        ).fetchall()
        budgets = conn.execute(
            "SELECT department, total_budget, spent_budget, remaining_budget FROM budgets"
        ).fetchall()
        balances = conn.execute(
            """
            SELECT e.id, e.name, e.department, b.annual_leave, b.sick_leave, b.casual_leave
            FROM employees e
            JOIN leave_balances b ON e.id = b.employee_id
            """
        ).fetchall()

    metrics = st.columns(4)
    metrics[0].metric("Total requests", total_requests)
    metrics[1].metric("Pending", pending_requests)
    metrics[2].metric("Completed", completed_requests)
    metrics[3].metric("Rejected / failed", unsuccessful_requests)

    audit_tab, analytics_tab = st.tabs(["Audit Trail", "Analytics"])

    with audit_tab:
        selected_request = st.selectbox(
            "Filter by request ID",
            ["All requests"] + request_ids,
        )

        query = """
            SELECT id, request_id, step_name, actor, action, details, timestamp
            FROM audit_log
        """
        params = []
        if selected_request != "All requests":
            query += " WHERE request_id = ?"
            params.append(selected_request)
        query += " ORDER BY id DESC LIMIT 100"

        with closing(get_db_connection()) as conn:
            logs = conn.execute(query, params).fetchall()

        if not logs:
            st.info("No audit events match this filter.")
        else:
            icons = {
                "Agent": "🤖",
                "Manager": "🛡️",
                "HR": "🏖️",
                "Finance": "💳",
                "Employee": "👤",
                "System": "⚙️",
            }
            for log in logs:
                step_name = log["step_name"].lower()
                if "classif" in step_name:
                    icon = "🔎"
                elif "manager" in step_name or "approval" in step_name:
                    icon = "🛡️"
                elif "hr" in step_name or "leave" in step_name:
                    icon = "🏖️"
                elif "finance" in step_name or "budget" in step_name:
                    icon = "💳"
                elif "notif" in step_name or "final" in step_name:
                    icon = "📨"
                else:
                    icon = icons.get(log["actor"], "⚙️")
                with st.container(border=True):
                    st.markdown(
                        f"**{icon} {log['step_name']}** · {log['actor']}"
                    )
                    st.caption(
                        f"{log['timestamp']} · {log['action']} · "
                        f"Request {log['request_id']}"
                    )
                    if log["details"]:
                        with st.expander("View event details"):
                            try:
                                st.json(json.loads(log["details"]))
                            except json.JSONDecodeError:
                                st.write(log["details"])

    with analytics_tab:
        type_counts = {row["workflow_type"]: row["count"] for row in requests_by_type}
        status_counts = {
            row["status"].replace("_", " ").title(): row["count"]
            for row in requests_by_status
        }
        type_data = {"Requests": type_counts or {"No requests": 0}}
        status_data = {"Requests": status_counts or {"No requests": 0}}
        chart_columns = st.columns(2)
        with chart_columns[0]:
            st.markdown("#### Requests per type")
            st.bar_chart(type_data)
        with chart_columns[1]:
            st.markdown("#### Requests per status")
            st.bar_chart(status_data)

    st.markdown("#### Department budgets and leave balances")
    budgets_tab, balances_tab = st.tabs(["Department budgets", "Leave balances"])

    with budgets_tab:
        for budget in budgets:
            percentage = (
                budget["spent_budget"] / budget["total_budget"]
                if budget["total_budget"] > 0
                else 0.0
            )
            st.write(
                f"**{budget['department']}** · "
                f"${budget['spent_budget']:,.2f} spent of "
                f"${budget['total_budget']:,.2f} · "
                f"${budget['remaining_budget']:,.2f} remaining"
            )
            st.progress(min(percentage, 1.0))

    with balances_tab:
        st.dataframe(
            [
                {
                    "ID": row["id"],
                    "Employee": row["name"],
                    "Department": row["department"],
                    "Annual leave": row["annual_leave"],
                    "Sick leave": row["sick_leave"],
                    "Casual leave": row["casual_leave"],
                }
                for row in balances
            ],
            use_container_width=True,
        )
