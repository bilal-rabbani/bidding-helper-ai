"""The Tender info tab: key facts (button) and the forms found in the document."""
import pandas as pd
import streamlit as st

from core.tender_index import page_label
from core.tender_qa import extract_key_facts


def tender_tab(tender, router, file_name=""):
    if tender is None:
        st.info("Upload a tender PDF to see its key facts and forms.")
        return
    known = sum(1 for p in tender.printed if p is not None)
    st.caption(f"Read {tender.n_pages} pages into {len(tender.passages)} passages. Printed page numbers were "
               f"found on {known} pages; pages are shown as 'PDF p.X (printed p.Y)' when the two differ.")

    st.subheader("Key facts")
    if router is None:
        st.info("Add your API keys in the sidebar to extract key facts.")
    if st.button("Extract key facts", disabled=router is None, key="kf_button"):
        with st.spinner("Reading the tender (3 short AI requests)..."):
            rows, notes = extract_key_facts(tender, router)
        st.session_state.key_facts = {"rows": rows, "notes": notes, "file": file_name}
        st.rerun()
    facts = st.session_state.get("key_facts")
    if facts and facts.get("file") == file_name:
        st.dataframe(pd.DataFrame(facts["rows"]), hide_index=True)
        st.caption("Check: 'verified' = the AI's exact words were found on the cited page. 'check' = look at "
                   "the page yourself before relying on it. 'not found' = the tender text does not state it.")
        for n in facts["notes"]:
            st.caption(n)

    st.subheader("Forms found in the document")
    if tender.forms:
        st.dataframe(pd.DataFrame([
            {"Form": f["label"], "Title": f["title"], "Page": page_label(f["pdf_page"], f["printed_page"])}
            for f in tender.forms]), hide_index=True)
        st.caption("Found by a program from the headings of the document. Ask in the Chat tab which of them "
                   "you must submit.")
    else:
        st.info("No form headings were found in this document.")
