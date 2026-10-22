"""
FlowPilot: Autonomous Workflow Agent
Main Streamlit Application Entry Point.
"""

import streamlit as st
from db.database import get_db_connection
from db.seed import ensure_database, seed_database
from ui.employee_view import render_employee_view
from ui.approver_view import render_approver_view
from ui.audit_view import render_audit_view
from ui.styles import apply_styles

# Initialize schema and seed sample data on first startup.
ensure_database()

# Page configuration
st.set_page_config(
    page_title="FlowPilot | Autonomous Workflow Agent",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

apply_styles()


def get_pending_count() -> int:
    """Helper to query the number of pending approvals."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM approvals WHERE decision = 'PENDING'")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0


# Sidebar Navigation
with st.sidebar:
    st.markdown("## ⚡ FlowPilot")
    st.caption("Workflows, moving forward.")

    pending_count = get_pending_count()
    approver_label = f"🛡️ Approver Dashboard ({pending_count})" if pending_count > 0 else "🛡️ Approver Dashboard"

    nav_selection = st.radio(
        "Navigate",
        [
            "👤 Employee Portal",
            approver_label,
            "📜 Audit & Reasoning Trail"
        ],
        index=0
    )

    with st.expander("Admin tools"):
        if st.button(
            "Reset / Re-seed Database",
            help="Restores default sample employees, balances, and budgets",
        ):
            seed_database()
            st.success("Database restored to its sample data.")
            st.rerun()


# Route Views
if nav_selection == "👤 Employee Portal":
    render_employee_view()
elif "Approver Dashboard" in nav_selection:
    render_approver_view()
elif "Audit" in nav_selection:
    render_audit_view()
