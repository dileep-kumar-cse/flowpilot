"""
FlowPilot Employee Portal
Allows employees to submit requests and track their status.
"""

from contextlib import closing

import streamlit as st

from agent.graph import run_workflow
from agent.tools import check_leave_balance
from db.database import get_db_connection
from ui.styles import render_request_timeline, render_status_badge


def render_employee_view():
    st.markdown("### Employee Portal")
    st.caption("Submit a request in plain English, or check the progress of one you have already submitted.")

    with closing(get_db_connection()) as conn:
        employees = conn.execute(
            "SELECT id, name, department, role FROM employees ORDER BY id ASC"
        ).fetchall()

    emp_options = {
        f"{employee['id']} - {employee['name']} ({employee['department']} {employee['role']})": employee["id"]
        for employee in employees
    }
    selected_label = st.selectbox(
        "Active employee",
        list(emp_options),
        index=0,
    )
    selected_emp_id = emp_options[selected_label]

    balance = check_leave_balance(selected_emp_id)
    if balance.get("success"):
        columns = st.columns(4)
        columns[0].metric("Annual leave", f"{balance['annual_leave']} days")
        columns[1].metric("Sick leave", f"{balance['sick_leave']} days")
        columns[2].metric("Casual leave", f"{balance['casual_leave']} days")
        columns[3].metric("Total available", f"{balance['total_available']} days")

    new_request, my_requests_tab = st.tabs(["New Request", "My Requests"])

    with new_request:
        st.markdown("#### Quick templates")
        template_columns = st.columns(3)
        preset_text = None
        if template_columns[0].button("3 days annual leave"):
            preset_text = "I need 3 days annual leave from Nov 15 for personal travel."
        if template_columns[1].button("2 monitors ($800)"):
            preset_text = "Purchase 2 Dell UltraSharp 4K monitors for $800 for the lab."
        if template_columns[2].button("2 days sick leave"):
            preset_text = "I need 2 days sick leave starting tomorrow due to flu."

        user_input = st.text_area(
            "Describe your request",
            value=preset_text or "",
            placeholder="For example: I need 2 days casual leave starting Monday",
            height=100,
        )

        if st.button("Submit request", type="primary", use_container_width=True):
            if not user_input.strip():
                st.error("Please enter a request description.")
            else:
                with st.spinner("FlowPilot is processing..."):
                    state = run_workflow(
                        raw_text=user_input.strip(),
                        employee_id=selected_emp_id,
                    )

                status = state.get("status")
                st.toast("Request submitted to FlowPilot.")
                if status == "pending_approval":
                    st.success(f"Request submitted for approval. Request ID: {state['request_id']}")
                elif status in ("completed", "approved"):
                    st.success(f"Request processed successfully. Request ID: {state['request_id']}")
                    st.balloons()
                else:
                    st.error(
                        f"Request could not be completed: "
                        f"{state.get('error_message') or status or 'Unknown status'}"
                    )
                with st.expander("Request details"):
                    st.write(f"**Request ID:** {state.get('request_id', 'N/A')}")
                    st.write(f"**Workflow:** {state.get('workflow_type', 'unknown').title()}")
                    st.write(f"**Current step:** {state.get('current_step', 'N/A')}")
                    st.json(state.get("extracted_data", {}))

    with my_requests_tab:
        with closing(get_db_connection()) as conn:
            requests = conn.execute(
                """
                SELECT id, workflow_type, raw_text, current_step, status, created_at, updated_at
                FROM requests
                WHERE employee_id = ?
                ORDER BY created_at DESC
                """,
                (selected_emp_id,),
            ).fetchall()
            notifications = conn.execute(
                """
                SELECT id, message, created_at
                FROM notifications
                WHERE employee_id = ?
                ORDER BY created_at DESC
                """,
                (selected_emp_id,),
            ).fetchall()

        if not requests:
            st.info("No requests submitted yet.")
        else:
            for request in requests:
                status = request["status"]

                with st.container(border=True):
                    st.markdown(f"**{request['workflow_type'].title()} request**")
                    render_status_badge(status)
                    st.caption(f"Request ID: {request['id']} · Submitted: {request['created_at']}")
                    st.write(request["raw_text"])
                    render_request_timeline(
                        request["workflow_type"],
                        status,
                        request["current_step"],
                    )
                    st.caption(f"Last updated: {request['updated_at']}")

        if notifications:
            with st.expander("Notifications"):
                for notification in notifications:
                    st.write(f"💬 {notification['message']}")
                    st.caption(f"{notification['created_at']} · Notification #{notification['id']}")
