"""
FlowPilot: Autonomous Workflow Agent
Main Streamlit Application Entry Point.
"""

import streamlit as st
from db.seed import ensure_database, seed_database
from ui.auth import authenticate_user, pages_for_role
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


def render_login() -> None:
    """Render the login form and place only safe user details in session state."""
    st.markdown("## Sign in to FlowPilot")
    with st.form("login_form"):
        username = st.text_input("Username", autocomplete="username")
        password = st.text_input(
            "Password",
            type="password",
            autocomplete="current-password",
        )
        submitted = st.form_submit_button("Log in", type="primary")
    if submitted:
        user = authenticate_user(username, password)
        if user is None:
            st.error("Invalid username or password. Please try again.")
        else:
            st.session_state["user"] = user
            st.rerun()


if "user" not in st.session_state:
    render_login()
    st.stop()

user = st.session_state["user"]
available_pages = pages_for_role(user["role"])
if not available_pages:
    st.session_state.pop("user", None)
    st.error("This account has no valid access role. Please sign in again.")
    st.stop()

# Sidebar Navigation
with st.sidebar:
    st.markdown("## ⚡ FlowPilot")
    st.caption("Workflows, moving forward.")
    st.caption(f"{user['username']} · {user['role'].title()}")
    if st.button("Logout", use_container_width=True):
        st.session_state.pop("user", None)
        st.rerun()

    nav_selection = st.radio(
        "Navigate",
        available_pages,
        index=0
    )

    if user["role"] == "manager":
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
