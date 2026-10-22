"""
FlowPilot Audit Log and Reasoning Viewer
Displays step-by-step agent decisions, LLM extractions, tool calls, and company status.
"""

import json
import streamlit as st
from db.database import get_db_connection


def render_audit_view():
    st.markdown("### 📜 Autonomous Agent Audit Trail & Reasoning")
    st.caption("Inspect real-time decision logs, tool interactions, and state machine transitions.")

    conn = get_db_connection()
    cursor = conn.cursor()

    # KPI Metrics
    cursor.execute("SELECT COUNT(*) FROM requests")
    total_reqs = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM requests WHERE status = 'pending_approval'")
    pending_reqs = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM requests WHERE status = 'completed'")
    completed_reqs = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM requests WHERE status IN ('rejected', 'failed')")
    failed_reqs = cursor.fetchone()[0]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Requests", total_reqs)
    m2.metric("Pending Approvals", pending_reqs)
    m3.metric("Completed", completed_reqs)
    m4.metric("Rejected / Failed", failed_reqs)

    st.markdown("---")

    # Filter by request ID
    cursor.execute("SELECT DISTINCT request_id FROM audit_log ORDER BY id DESC")
    req_ids = [r[0] for r in cursor.fetchall()]

    col_filter, col_actor = st.columns(2)
    selected_req = col_filter.selectbox("Filter by Request ID:", ["All Requests"] + req_ids)
    selected_actor = col_actor.selectbox("Filter by Actor:", ["All Actors", "Agent", "Manager", "HR", "Finance", "Employee", "System"])

    # Query audit logs
    query = "SELECT id, request_id, step_name, actor, action, details, timestamp FROM audit_log"
    params = []
    conditions = []

    if selected_req != "All Requests":
        conditions.append("request_id = ?")
        params.append(selected_req)

    if selected_actor != "All Actors":
        conditions.append("actor = ?")
        params.append(selected_actor)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY id DESC LIMIT 50"

    cursor.execute(query, params)
    logs = cursor.fetchall()
    conn.close()

    if not logs:
        st.info("No audit logs found for the selected filter.")
    else:
        for log in logs:
            actor = log["actor"]
            actor_color = {
                "Agent": "#6366f1",     # Indigo
                "Manager": "#0ea5e9",   # Sky
                "HR": "#ec4899",        # Pink
                "Finance": "#10b981",   # Emerald
                "Employee": "#f59e0b",  # Amber
                "System": "#64748b"     # Slate
            }.get(actor, "#64748b")

            with st.container():
                st.markdown(
                    f"""
                    <div style="border-left: 4px solid {actor_color}; padding: 10px 15px; margin-bottom: 8px; background-color: #f8fafc; border-radius: 4px;">
                        <span style="background-color:{actor_color}; color:#fff; padding:2px 8px; border-radius:12px; font-size:11px; font-weight:bold;">{actor}</span>
                        <span style="font-weight:bold; margin-left:8px; color:#1e293b;">{log['step_name']}</span>
                        <code style="margin-left:6px; font-size:12px;">{log['action']}</code>
                        <span style="float:right; color:#94a3b8; font-size:12px;">{log['timestamp']}</span>
                        <div style="margin-top:6px; font-size:13px; color:#334155;">
                            <b>Request:</b> <code>{log['request_id']}</code>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                if log["details"]:
                    try:
                        parsed_details = json.loads(log["details"])
                        with st.expander("🔍 View Step Reasoning & Parameters"):
                            st.json(parsed_details)
                    except Exception:
                        st.caption(f"Details: {log['details']}")

    # Company Financial & HR State Overview
    st.markdown("---")
    st.markdown("#### 🏢 Departmental Budgets & Employee Balances")
    tab_budgets, tab_balances = st.tabs(["💰 Department Budgets", "🏖️ Leave Balances"])

    conn = get_db_connection()
    with tab_budgets:
        cursor = conn.cursor()
        cursor.execute("SELECT department, total_budget, spent_budget, remaining_budget FROM budgets")
        budgets = cursor.fetchall()
        for b in budgets:
            pct = (b['spent_budget'] / b['total_budget']) if b['total_budget'] > 0 else 0.0
            st.write(f"**{b['department']}**: ${b['spent_budget']:,.2f} spent of ${b['total_budget']:,.2f} (Remaining: **${b['remaining_budget']:,.2f}**)")
            st.progress(min(pct, 1.0))

    with tab_balances:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT e.id, e.name, e.department, b.annual_leave, b.sick_leave, b.casual_leave
            FROM employees e
            JOIN leave_balances b ON e.id = b.employee_id
            """
        )
        bals = cursor.fetchall()
        bal_data = [
            {
                "ID": row["id"],
                "Employee": row["name"],
                "Department": row["department"],
                "Annual Leave": row["annual_leave"],
                "Sick Leave": row["sick_leave"],
                "Casual Leave": row["casual_leave"]
            }
            for row in bals
        ]
        st.dataframe(bal_data, use_container_width=True)

    conn.close()
