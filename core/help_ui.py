"""The Help tab: the user guide and the known limits, read from the docs folder."""
from pathlib import Path

import streamlit as st

DOCS = Path(__file__).resolve().parent.parent / "docs"


def _read(name: str) -> str:
    try:
        return (DOCS / name).read_text(encoding="utf-8")
    except OSError:
        return f"({name} was not found.)"


def help_tab():
    guide, limits = st.tabs(["User guide", "Known limits"])
    with guide:
        st.markdown(_read("USER_GUIDE.md"))
    with limits:
        st.markdown(_read("KNOWN_LIMITS.md"))
