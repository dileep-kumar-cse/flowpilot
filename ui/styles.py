"""Shared visual styling for FlowPilot's Streamlit interface."""

from html import escape

import streamlit as st


def apply_styles() -> None:
    """Inject the glass theme and small reusable request-status components."""
    st.markdown(
        """
        <style>
        @keyframes flowpilot-gradient {
            0%, 100% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
        }
        @keyframes flowpilot-float {
            0%, 100% { transform: translate3d(0, 0, 0) scale(1); }
            50% { transform: translate3d(35px, -28px, 0) scale(1.08); }
        }
        @keyframes flowpilot-enter {
            from { opacity: 0; transform: translateY(14px); }
            to { opacity: 1; transform: translateY(0); }
        }
        @keyframes flowpilot-pulse {
            0%, 100% { box-shadow: 0 0 0 0 rgba(250, 204, 21, .7); }
            50% { box-shadow: 0 0 0 6px rgba(250, 204, 21, 0); }
        }

        .stApp {
            background: linear-gradient(125deg, #0b1020, #11132e, #101c35, #17102e);
            background-size: 300% 300%;
            animation: flowpilot-gradient 18s ease infinite;
        }
        body::before, body::after {
            content: "";
            position: fixed;
            z-index: 0;
            width: 340px;
            height: 340px;
            border-radius: 50%;
            filter: blur(95px);
            opacity: .28;
            pointer-events: none;
            animation: flowpilot-float 22s ease-in-out infinite;
        }
        body::before { top: 8%; left: 12%; background: #8b5cf6; }
        body::after {
            right: 8%;
            bottom: 5%;
            background: #22d3ee;
            animation-delay: -11s;
        }
        section[data-testid="stSidebar"], .stMain {
            position: relative;
            z-index: 1;
        }
        section[data-testid="stSidebar"] {
            background: rgba(13, 19, 39, .68);
            border-right: 1px solid rgba(226, 232, 255, .1);
            backdrop-filter: blur(24px);
        }
        .stMainBlockContainer {
            animation: flowpilot-enter .65s ease-out both;
        }
        h1, h2 {
            background: linear-gradient(100deg, #c4b5fd, #67e8f9);
            background-clip: text;
            -webkit-background-clip: text;
            color: transparent;
            -webkit-text-fill-color: transparent;
        }

        /* Shared glass treatment for cards, forms, metrics, and expanders. */
        div[data-testid="stVerticalBlockBorderWrapper"],
        div[data-testid="stMetric"],
        div[data-testid="stExpander"],
        div[data-testid="stForm"] {
            border: 1px solid rgba(226, 232, 255, .13);
            border-radius: 18px;
            background: rgba(22, 29, 55, .55);
            box-shadow: 0 10px 35px rgba(0, 0, 0, .2);
            backdrop-filter: blur(18px);
            transition: transform .22s ease, border-color .22s ease, box-shadow .22s ease;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:hover,
        div[data-testid="stMetric"]:hover,
        div[data-testid="stExpander"]:hover {
            transform: translateY(-3px) scale(1.01);
            border-color: rgba(103, 232, 249, .35);
            box-shadow: 0 14px 40px rgba(139, 92, 246, .16);
        }
        div[data-testid="stMetric"] { padding: 14px 16px; }

        /* Keep long values such as "12 days" visible in narrow metric cards. */
        div[data-testid="stMetricValue"],
        div[data-testid="stMetricValue"] > div {
            max-width: 100%;
            overflow: visible !important;
            white-space: normal !important;
            overflow-wrap: anywhere;
            text-overflow: clip !important;
            font-size: clamp(1.05rem, 1.8vw, 1.55rem) !important;
            line-height: 1.2;
        }
        div[data-testid="stMetricLabel"] {
            white-space: normal !important;
            overflow-wrap: anywhere;
        }

        div.stButton > button {
            border: 1px solid rgba(103, 232, 249, .25);
            border-radius: 12px;
            background: linear-gradient(110deg, #7c3aed, #0891b2);
            color: #fff;
            font-weight: 700;
            transition: transform .16s ease, box-shadow .16s ease, filter .16s ease;
        }
        div.stButton > button:hover {
            transform: scale(1.025);
            box-shadow: 0 0 22px rgba(34, 211, 238, .35);
            filter: brightness(1.12);
            color: #fff;
            border-color: rgba(103, 232, 249, .6);
        }
        div.stButton > button:active { transform: scale(.97); }

        input, textarea, div[data-baseweb="select"] > div {
            border-radius: 12px !important;
            background: rgba(9, 14, 30, .55) !important;
        }
        input:focus, textarea:focus, div[data-baseweb="select"]:focus-within {
            border-color: #22d3ee !important;
            box-shadow: 0 0 0 1px #22d3ee, 0 0 18px rgba(34, 211, 238, .2) !important;
        }
        button[data-baseweb="tab"] {
            transition: color .18s ease, background .18s ease;
            border-radius: 10px 10px 0 0;
        }
        button[data-baseweb="tab"]:hover {
            color: #67e8f9;
            background: rgba(139, 92, 246, .12);
        }
        .status-badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 5px 11px;
            border: 1px solid currentColor;
            border-radius: 999px;
            font-size: .82rem;
            font-weight: 700;
        }
        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: currentColor;
        }
        .status-pending { color: #facc15; }
        .status-pending .status-dot { animation: flowpilot-pulse 1.8s infinite; }
        .status-approved { color: #4ade80; }
        .status-rejected, .status-failed { color: #fb7185; }

        .request-timeline {
            display: flex;
            align-items: center;
            gap: 8px;
            margin: 15px 0 4px;
            color: #8b95b5;
            font-size: .82rem;
        }
        .request-step { display: flex; align-items: center; gap: 6px; white-space: nowrap; }
        .request-step.is-complete { color: #67e8f9; }
        .request-step.is-current { color: #c4b5fd; font-weight: 700; }
        .request-connector {
            flex: 1;
            min-width: 10px;
            height: 1px;
            background: rgba(226, 232, 255, .2);
        }
        .request-connector.is-complete {
            background: linear-gradient(90deg, #8b5cf6, #22d3ee);
        }
        @media (max-width: 640px) {
            .request-timeline { gap: 4px; font-size: .7rem; }
            .request-step { gap: 3px; }
        }
        @media (prefers-reduced-motion: reduce) {
            *, *::before, *::after {
                animation-duration: .01ms !important;
                animation-iteration-count: 1 !important;
                scroll-behavior: auto !important;
                transition-duration: .01ms !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_status_badge(status: str) -> None:
    """Render a compact, color-coded workflow status."""
    if status == "pending_approval":
        label, css_class = "Pending", "status-pending"
    elif status in ("approved", "completed"):
        label, css_class = "Approved", "status-approved"
    elif status == "rejected":
        label, css_class = "Rejected", "status-rejected"
    else:
        label, css_class = escape(status.replace("_", " ").title()), "status-failed"

    st.markdown(
        f'<span class="status-badge {css_class}">'
        f'<span class="status-dot"></span>{label}</span>',
        unsafe_allow_html=True,
    )


def render_request_timeline(workflow_type: str, status: str, current_step: str) -> None:
    """Show progress through submission, approval, department review, and completion."""
    department_step = "HR" if workflow_type == "leave" else "Finance"
    supported = workflow_type in ("leave", "purchase")
    submitted = True
    manager_done = supported and status != "pending_approval"
    department_done = supported and status in ("approved", "completed")
    done = status in ("completed", "rejected", "failed")

    steps = [
        ("Submitted", submitted, False),
        ("Manager", manager_done, status == "pending_approval"),
        (department_step, department_done, current_step in ("hr_balance_check", "finance_budget_check")),
        ("Done", done, False),
    ]

    timeline = ['<div class="request-timeline">']
    for index, (label, complete, current) in enumerate(steps):
        state_class = "is-complete" if complete else ("is-current" if current else "")
        icon = "✓" if complete else ("●" if current else "○")
        timeline.append(
            f'<span class="request-step {state_class}">{icon} {escape(label)}</span>'
        )
        if index < len(steps) - 1:
            connector_class = "is-complete" if complete else ""
            timeline.append(f'<span class="request-connector {connector_class}"></span>')
    timeline.append("</div>")
    st.markdown("".join(timeline), unsafe_allow_html=True)
