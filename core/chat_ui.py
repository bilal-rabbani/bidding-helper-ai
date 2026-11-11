"""The Chat tab of the app."""
import pandas as pd
import streamlit as st

from core.boq_edit import StalePlanError
from core.chat import handle_message


def _add(role, content, **extra):
    st.session_state.chat.append({"role": role, "content": content, **extra})


def chat_tab(table, session, idx, router, file_name="", tender=None):
    st.session_state.setdefault("chat", [])
    st.session_state.setdefault("chat_plan", None)
    if router is None:
        st.info("To chat, add your API keys in the sidebar and press 'Use and test keys'. "
                "You can already type 'undo' or 'help', and the 'Edit rates' tab works without keys.")
    if not st.session_state.chat:
        st.write("Ask me to edit the BOQ, for example: **increase items 3 to 5 by 10%**. "
                 "Type **help** to see what I can do.")
    for m in st.session_state.chat:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            if m.get("rows"):
                st.dataframe(pd.DataFrame(m["rows"]), hide_index=True)
            if m.get("notes"):
                st.caption(" | ".join(m["notes"]))

    pending = st.session_state.chat_plan
    if pending is not None and pending["table"] == idx:
        plan = pending["plan"]
        a, b = st.columns(2)
        if a.button("Apply these changes", key=f"chat_apply_{idx}", type="primary",
                    disabled=not plan.changes):
            try:
                n = session.apply(plan)
                _add("assistant", f"Done: {plan.command.label()} on {n} row(s). "
                                  "The Excel download at the top includes this change.")
            except StalePlanError as e:
                _add("assistant", str(e))
            st.session_state.chat_plan = None
            st.rerun()
        if b.button("Cancel", key=f"chat_cancel_{idx}"):
            _add("assistant", "Cancelled. Nothing was changed.")
            st.session_state.chat_plan = None
            st.rerun()

    text = st.chat_input("Type a message, for example: increase items 3 to 5 by 10%")
    if text:
        history = list(st.session_state.chat)
        _add("user", text)
        with st.spinner("Thinking..."):
            reply = handle_message(text, table, session, router, history, tender)
        _add("assistant", reply.text, rows=reply.rows, notes=reply.notes)
        st.session_state.chat_plan = {"plan": reply.plan, "table": idx} if reply.plan else None
        st.rerun()
    if st.session_state.chat and st.button("Clear chat", key=f"chat_clear_{idx}"):
        st.session_state.chat, st.session_state.chat_plan = [], None
        st.rerun()
