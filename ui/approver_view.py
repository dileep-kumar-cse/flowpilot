"""
FlowPilot Approver Dashboard View
Allows Managers and Department Heads to review pending workflow approvals,
make decisions (Approve/Reject with comments), and trigger agent resumption.
"""

import json
import streamlit as st
from db.database import get_db_connection
from agent.graph import resume_workflow


def render_approver_view():
    st.markdown("### 🛡️ Approver Dashboard")
    st.caption("Review pending requests requiring human approval. Decisions resume autonomous execution.")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, department, role FROM employees WHERE role IN ('Manager', 'HR', 'Finance') ORDER BY id ASC")
    approvers = cursor.fetchall()
    conn.close()

    approver_options = {f"{a['name']} ({a['role']} - {a['department']})": a['id'] for a in approvers}
    selected_label = st.selectbox("Active Approver Profile:", list(approver_options.keys()), index=0)
    selected_approver_id = approver_options[selected_label]

    # Query pending approvals
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT 
            a.id as approval_id,
            a.request_id,
            a.approver_role,
            a.decision,
            a.created_at as requested_at,
            r.employee_id,
            r.workflow_type,
            r.raw_text,
            r.structured_data,
            e.name as employee_name,
            e.department as employee_dept
        FROM approvals a
        JOIN requests r ON a.request_id = r.id
        JOIN employees e ON r.employee_id = e.id
        WHERE a.decision = 'PENDING'
        ORDER BY a.created_at ASC
        """
    )
    pending_items = cursor.fetchall()
    conn.close()

    st.markdown(f"#### ⏳ Pending Approvals ({len(pending_items)})")

    if not pending_items:
        st.success("🎉 All caught up! No pending approvals waiting for review.")
    else:
        for item in pending_items:
            req_id = item["request_id"]
            wf_type = item["workflow_type"]
            data = json.loads(item["structured_data"]) if item["structured_data"] else {}

            with st.container():
                st.markdown(
                    f"""
                    <div style="border:1px solid #e0e0e0; border-radius:8px; padding:16px; margin-bottom:12px; background-color:#ffffff;">
                        <span style="background-color:#ffeedd; color:#b35900; font-weight:bold; padding:4px 8px; border-radius:4px; font-size:12px;">PENDING APPROVAL</span>
                        <h4 style="margin:8px 0 4px 0;">Request ID: <code>{req_id}</code></h4>
                        <p style="margin:0 0 8px 0; color:#555;"><b>Requester:</b> {item['employee_name']} ({item['employee_dept']}) | <b>Workflow:</b> {wf_type.upper()}</p>
                        <p style="background-color:#f8f9fa; padding:8px; border-radius:6px; font-style:italic;">"{item['raw_text']}"</p>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                # Show structured breakdown
                col_info, col_actions = st.columns([2, 1])
                with col_info:
                    if wf_type == "leave":
                        st.write(f"📅 **Days Requested:** {data.get('days', 1)} | **Type:** {data.get('leave_type', 'annual')} | **Start:** {data.get('start_date', 'N/A')}")
                    elif wf_type == "purchase":
                        amount = float(data.get('amount', 0.0))
                        st.write(f"💳 **Item:** {data.get('item', 'Item')} | **Amount:** ${amount:,.2f} | **Department:** {data.get('department', 'N/A')}")

                with col_actions:
                    comment_key = f"comment_{req_id}"
                    comment = st.text_input("Comment (optional):", key=comment_key, placeholder="e.g. Approved")
                    
                    btn_col1, btn_col2 = st.columns(2)
                    if btn_col1.button("✅ Approve", key=f"app_{req_id}", type="primary", use_container_width=True):
                        with st.spinner("Processing approval and resuming agent..."):
                            final_state = resume_workflow(
                                request_id=req_id,
                                decision="APPROVED",
                                comments=comment.strip() or "Approved by manager",
                                approver_id=selected_approver_id
                            )
                            st.success(f"Request {req_id} APPROVED! Workflow finalized as {final_state['status']}.")
                            st.rerun()

                    if btn_col2.button("❌ Reject", key=f"rej_{req_id}", use_container_width=True):
                        with st.spinner("Processing rejection and resuming agent..."):
                            final_state = resume_workflow(
                                request_id=req_id,
                                decision="REJECTED",
                                comments=comment.strip() or "Rejected by manager",
                                approver_id=selected_approver_id
                            )
                            st.error(f"Request {req_id} REJECTED. Workflow marked as rejected.")
                            st.rerun()

                st.divider()

    # Past Approvals History
    with st.expander("📜 Recent Approval History"):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT a.id, a.request_id, a.decision, a.comments, a.decided_at, e.name as approver_name
            FROM approvals a
            LEFT JOIN employees e ON a.approver_id = e.id
            WHERE a.decision != 'PENDING'
            ORDER BY a.decided_at DESC
            LIMIT 10
            """
        )
        history = cursor.fetchall()
        conn.close()

        if not history:
            st.info("No approval actions recorded yet.")
        else:
            for h in history:
                badge = "🟢 APPROVED" if h["decision"] == "APPROVED" else "🔴 REJECTED"
                st.write(f"**{h['request_id']}** — {badge} by {h['approver_name'] or 'Approver'} on {h['decided_at']}")
                if h["comments"]:
                    st.caption(f"Comment: {h['comments']}")
