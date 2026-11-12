"""The Urdu tab: translate item descriptions, read them next to the English, and correct them."""
import pandas as pd
import streamlit as st

from core.boq_edit import Selector
from core.urdu import (DEFAULT_GLOSSARY, parse_glossary, set_urdu, translate_rows, urdu_check_for,
                       urdu_for)


def urdu_tab(table, router):
    st.write("Translate the item descriptions into Urdu. The AI makes the translation, so please read it "
             "(or have it read) before using it. Rows with a note in the Check column have a problem the "
             "program noticed.")
    with st.expander("Glossary: your preferred Urdu words (one per line: english = اردو)"):
        text = st.text_area("Glossary", value=getattr(table, "urdu_glossary", DEFAULT_GLOSSARY),
                            height=260, key="urdu_glossary_text", label_visibility="collapsed")
        table.urdu_glossary = text

    scope = st.radio("Which items?", ["All items", "Only the rows I name"], horizontal=True, key="urdu_scope")
    rows = table.items
    if scope != "All items":
        c1, c2, c3 = st.columns(3)
        numbers = c1.text_input("Sr. Nos", placeholder="3, 5, 10-12", key="urdu_nums")
        words = c2.text_input("Words in the description", placeholder="door; aluminium", key="urdu_words")
        sections = c3.text_input("Section", placeholder="electrical works", key="urdu_sections")
        try:
            selector = Selector.from_spec(numbers=numbers, keywords=words, sections=sections)
            rows = [] if selector.is_empty() else [r for r in table.items if selector.matches(r)]
        except ValueError as e:
            rows = []
            st.error(str(e))
    todo = [r for r in rows if not urdu_for(r)]
    st.caption(f"{len(rows)} item(s) selected, {len(todo)} still without a translation "
               f"(about {max(1, -(-len(todo) // 6)) if todo else 0} AI request(s)).")
    again = st.checkbox("Translate again, even where a translation exists", key="urdu_force")
    if router is None:
        st.info("Add your API keys in the sidebar to translate.")
    if st.button("Translate", disabled=router is None or not rows, key="urdu_go"):
        with st.spinner("Translating..."):
            stats, notes = translate_rows(rows, router, parse_glossary(text), force=again)
        st.session_state.urdu_msg = (f"Translated {stats['done']} of {stats['asked']}; {stats['check']} need a "
                                     f"check; {stats['failed']} failed." + ("  " + " ".join(notes) if notes else ""))
        st.rerun()
    if st.session_state.get("urdu_msg"):
        st.success(st.session_state.urdu_msg)

    done = [r for r in table.items if urdu_for(r)]
    if not done:
        st.info("No translations yet.")
        return
    df = pd.DataFrame([{"Sr. No": r.sr_no, "English": r.description, "Urdu": urdu_for(r),
                        "Check": urdu_check_for(r)} for r in done])
    edited = st.data_editor(df, hide_index=True, disabled=["Sr. No", "English", "Check"], key="urdu_editor",
                            column_config={"English": st.column_config.TextColumn("English", width="large"),
                                           "Urdu": st.column_config.TextColumn("Urdu", width="large")})
    if st.button("Save my corrections", key="urdu_save"):
        changed = 0
        for i, row in enumerate(done):
            new = str(edited.iloc[i]["Urdu"] or "").strip()
            if new and new != urdu_for(row):
                set_urdu(row, new, "edited by you")
                changed += 1
        st.session_state.urdu_msg = f"Saved {changed} correction(s)."
        st.rerun()
    st.caption("The Excel file has a 'BOQ Urdu' sheet with these translations (Download Excel at the top).")
