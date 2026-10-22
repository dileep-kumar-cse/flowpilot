"""Small shared styling for the Streamlit interface."""

import streamlit as st


def apply_styles() -> None:
    st.markdown(
        """
        <style>
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 14px;
            box-shadow: 0 3px 14px rgba(31, 41, 55, 0.07);
        }
        div[data-testid="stVerticalBlock"] {
            gap: 0.9rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
