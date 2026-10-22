"""
FlowPilot: Autonomous Workflow Agent
Main Streamlit Application Entry Point.
"""

import streamlit as st
from db.database import init_db, get_db_connection
from db.seed import seed_database
from ui.employee_view import render_employee_view
from ui.approver_view import render_approver_view
from ui.audit_view import render_audit_view

# Initialize database schema if not present
init_db()

# Page configuration
st.set_page_config(
    page_title="FlowPilot | Autonomous Workflow Agent",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        background: linear-gradient(90deg, #4f46e5, #06b6d4);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0px;
    }
    .sub-header {
        font-size: 0.95rem;
        color: #64748b;
        margin-bottom: 20px;
    }
    .metric-card {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 12px;
    }
    div[data-testid="stSidebarNav"] {
        display: none;
    }
</style>
""", unsafe_allow_html=True)


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
    st.markdown('<p class="main-header">⚡ FlowPilot</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Autonomous Business Workflow Agent</p>', unsafe_allow_html=True)
    st.caption("Powered by LangGraph & Free-Tier Gemini")

    pending_count = get_pending_count()
    approver_label = f"🛡️ Approver Dashboard ({pending_count})" if pending_count > 0 else "🛡️ Approver Dashboard"

    nav_selection = st.radio(
        "Navigation",
        [
            "👤 Employee Portal",
            approver_label,
            "📜 Audit & Reasoning Trail"
        ],
        index=0
    )

    st.markdown("---")
    st.markdown("##### ⚙️ System Controls")

    if st.button("🔄 Reset / Re-seed Database", help="Restores default sample employees, balances, and budgets"):
        seed_database()
        st.success("Database restored to initial seed state!")
        st.rerun()

    st.caption("🟢 **Engine Status:** Online")
    st.caption("🔒 **Security:** .env protected | 100% Free Tools")


# Route Views
if nav_selection == "👤 Employee Portal":
    render_employee_view()
elif "Approver Dashboard" in nav_selection:
    render_approver_view()
elif "Audit" in nav_selection:
    render_audit_view()
