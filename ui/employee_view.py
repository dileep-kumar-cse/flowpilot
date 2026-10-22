"""
FlowPilot Employee Portal View
Allows employees to submit natural language workflow requests, track statuses,
and view in-app notifications.
"""

import json
import streamlit as st
from db.database import get_db_connection
from agent.graph import run_workflow
from agent.tools import check_leave_balance


def render_employee_view():
    st.markdown("### 👤 Employee Portal")
    st.caption("Submit business requests in plain English. FlowPilot AI will classify, route, and orchestrate approvals.")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, department, role FROM employees ORDER BY id ASC")
    employees = cursor.fetchall()
    conn.close()

    emp_options = {f"{e['id']} - {e['name']} ({e['department']} {e['role']})": e['id'] for e in employees}
    selected_label = st.selectbox("Select Active Employee:", list(emp_options.keys()), index=3) # Default EMP001 (Alice)
    selected_emp_id = emp_options[selected_label]

    # Show employee balance & department context
    bal_res = check_leave_balance(selected_emp_id)
    if bal_res.get("success"):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🌴 Annual Leave", f"{bal_res['annual_leave']} days")
        c2.metric("🩺 Sick Leave", f"{bal_res['sick_leave']} days")
        c3.metric("☕ Casual Leave", f"{bal_res['casual_leave']} days")
        c4.metric("📊 Total Available", f"{bal_res['total_available']} days")

    st.markdown("---")

    # Quick prompt presets
    st.markdown("##### ⚡ Quick Templates")
    col1, col2, col3 = st.columns(3)
    preset_text = None
    if col1.button("🏖️ 3 Days Annual Leave"):
        preset_text = "I need 3 days annual leave from Nov 15 for personal travel."
    if col2.button("💻 Purchase 2 Monitors ($800)"):
        preset_text = "Purchase 2 Dell UltraSharp 4K monitors for $800 for the lab."
    if col3.button("🩺 2 Days Sick Leave"):
        preset_text = "I need 2 days sick leave starting tomorrow due to flu."

    default_input = preset_text if preset_text else ""
    user_input = st.text_area(
        "Describe your request in natural language:",
        value=default_input,
        placeholder="e.g. 'I need 2 days casual leave starting Monday' or 'Purchase 1 ergonomic chair for $350'",
        height=90
    )

    if st.button("🚀 Submit to FlowPilot Agent", type="primary", use_container_width=True):
        if not user_input.strip():
            st.warning("Please enter a request description.")
        else:
            with st.spinner("🤖 FlowPilot Agent is reasoning, classifying, and orchestrating workflow..."):
                state = run_workflow(raw_text=user_input.strip(), employee_id=selected_emp_id)
                st.session_state["last_submission"] = state

    # Display last submission result card if available
    if "last_submission" in st.session_state:
        sub = st.session_state["last_submission"]
        st.markdown("---")
        st.markdown("#### 🤖 Agent Execution Result")
        
        status = sub.get("status", "draft")
        status_color = {
            "pending_approval": "orange",
            "completed": "green",
            "approved": "blue",
            "rejected": "red",
            "failed": "red"
        }.get(status, "gray")

        st.markdown(
            f"""
            <div style="padding:15px; border-radius:10px; border:1px solid #ddd; background-color:#f9fafb; margin-bottom:15px;">
                <h4 style="margin:0; color:#111;">Request ID: <code>{sub.get('request_id')}</code></h4>
                <p style="margin:5px 0;"><b>Workflow Type:</b> <span style="text-transform:uppercase; font-weight:bold;">{sub.get('workflow_type')}</span> | 
                <b>Current Step:</b> <code>{sub.get('current_step')}</code> | 
                <b>Status:</b> <span style="color:{status_color}; font-weight:bold; text-transform:uppercase;">{status}</span></p>
            </div>
            """,
            unsafe_allow_html=True
        )

        with st.expander("🔍 View Agent Extracted Data & Reasoning", expanded=True):
            st.json(sub.get("extracted_data", {}))

    # Request History & In-App Notifications
    st.markdown("---")
    tab_history, tab_notifs = st.tabs(["📋 My Request History", "🔔 My Notifications"])

    with tab_history:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, workflow_type, raw_text, current_step, status, created_at, updated_at
            FROM requests
            WHERE employee_id = ?
            ORDER BY created_at DESC
            """,
            (selected_emp_id,)
        )
        my_requests = cursor.fetchall()
        conn.close()

        if not my_requests:
            st.info("No requests submitted yet.")
        else:
            for req in my_requests:
                color = "orange" if "pending" in req["status"] else ("green" if req["status"] == "completed" else "red")
                with st.expander(f"📌 {req['id']} | {req['workflow_type'].upper()} | {req['created_at']}"):
                    st.write(f"**Request:** {req['raw_text']}")
                    st.markdown(f"**Status:** :{color}[**{req['status'].upper()}**] (Step: `{req['current_step']}`)")
                    st.caption(f"Last updated: {req['updated_at']}")

    with tab_notifs:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, message, created_at, is_read
            FROM notifications
            WHERE employee_id = ?
            ORDER BY created_at DESC
            """,
            (selected_emp_id,)
        )
        notifs = cursor.fetchall()
        conn.close()

        if not notifs:
            st.info("No notifications received.")
        else:
            for n in notifs:
                st.markdown(f"💬 **{n['message']}**")
                st.caption(f"Time: {n['created_at']} | Notification #{n['id']}")
                st.divider()
