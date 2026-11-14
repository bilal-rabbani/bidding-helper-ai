"""Sidebar part of the app: save the work to a file, or continue from one."""
from pathlib import Path

import streamlit as st

from core.session_file import SessionFileError, load_session, to_session_bytes


def _restore(data, pdf_upload):
    s = st.session_state
    s.result, s.sessions, s.tender = data.result, data.sessions, data.tender
    s.file_name = data.file_name or "session"
    s.chat, s.chat_plan, s.key_facts = data.chat, None, data.key_facts
    s.plan, s.plan_table, s.pdf_bytes = None, None, None
    # a PDF still sitting in the upload box must not replace the session that was just loaded
    s.file_id = ((pdf_upload.name, pdf_upload.size) if pdf_upload is not None
                 else ("session", data.file_name, data.saved_at))
    s.pop("urdu_msg", None)
    s.pop("urdu_glossary_text", None)
    glossary = next((t.urdu_glossary for t in data.result.tables if getattr(t, "urdu_glossary", None)), None)
    if glossary:
        s["urdu_glossary_text"] = glossary
    s.message = (f"Session loaded: {len(data.result.tables)} BOQ table(s), saved {data.saved_at}. "
                 "The undo history is not kept in a session file.")


def session_sidebar(pdf_upload=None):
    st.sidebar.header("3. Save or continue your work")
    st.sidebar.caption("The session file holds your edits, chat, Urdu translations, key facts and the tender "
                       "text, never your API keys. It contains your rates, so keep it private.")
    result = st.session_state.get("result")
    if result is not None:
        stem = Path(st.session_state.get("file_name") or "tender").stem
        st.sidebar.download_button(
            "Save session file",
            data=to_session_bytes(result, st.session_state.get("file_name", ""),
                                  st.session_state.get("chat", []), st.session_state.get("key_facts")),
            file_name=f"{stem}_session.json", mime="application/json", key="session_download")
    else:
        st.sidebar.caption("Upload a tender first, then you can save your work here.")

    loaded = st.sidebar.file_uploader("Continue from a session file", type=["json"], key="session_uploader")
    if loaded is None:
        st.session_state.session_file_id = None
        st.session_state.pop("session_error", None)
    else:
        fid = (loaded.name, loaded.size)
        if st.session_state.get("session_file_id") != fid:
            st.session_state.session_file_id = fid
            try:
                data = load_session(loaded.getvalue())
            except SessionFileError as e:
                st.session_state.session_error = str(e)
            else:
                st.session_state.pop("session_error", None)
                _restore(data, pdf_upload)
                st.rerun()
    if st.session_state.get("session_error"):
        st.sidebar.error(st.session_state.session_error)
