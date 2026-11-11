"""Bidding Helper AI - the Streamlit app (phase 4b)."""
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from core.app_helpers import (OPERATIONS, build_command, fmt, items_frame, review_frame,
                              show_value)
from core.boq_edit import NUMERIC_FIELDS, EditSession, Selector, StalePlanError
from core.boq_parser import parse_boq
from core.chat_ui import chat_tab
from core.excel_export import boq_excel_bytes
from core.llm_router import LLMError, LLMRouter

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

st.set_page_config(page_title="Bidding Helper AI", layout="wide")

DEFAULTS = {"result": None, "sessions": [], "file_id": None, "file_name": "", "pdf_bytes": None,
            "router": None, "key_report": [], "plan": None, "plan_table": None, "message": None}
for _key, _value in DEFAULTS.items():
    st.session_state.setdefault(_key, _value)


# ----------------------------------------------------------------- sidebar
def sidebar():
    st.sidebar.title("Bidding Helper AI")
    st.sidebar.header("1. Tender PDF")
    uploaded = st.sidebar.file_uploader("Upload a tender PDF", type=["pdf"])
    if uploaded is not None and st.sidebar.button("Re-read the PDF (discards my edits)"):
        st.session_state.file_id = None

    st.sidebar.header("2. API keys")
    st.sidebar.caption("Free keys from Gemini and Groq. Put several keys in one box, separated "
                       "by commas. Keys stay in this browser session only and are never saved.")
    gemini = st.sidebar.text_input("Gemini keys", type="password", key="gemini_keys")
    groq = st.sidebar.text_input("Groq keys", type="password", key="groq_keys")
    if st.sidebar.button("Use and test keys"):
        router = LLMRouter({"gemini": gemini, "groq": groq})
        if not router.keys:
            st.session_state.router, st.session_state.key_report = None, []
            st.sidebar.warning("Enter at least one key.")
        else:
            with st.spinner("Checking your keys..."):
                report = router.test_keys()
            st.session_state.router, st.session_state.key_report = router, report

    router = st.session_state.router
    if router is not None:
        for row in st.session_state.key_report:
            icon = "\u2705 " if row["status"] == "ok" else "\u274c "
            st.sidebar.write(f"{icon}{row['label']}: {row['message']}")
        for provider in router.keys:
            try:
                names = router.list_models(provider)
                default = router.models.get(provider) or router.model_for(provider)
            except LLMError as e:
                st.sidebar.warning(f"{provider.title()}: could not load the model list. {e}")
                continue
            if not names:
                st.sidebar.warning(f"{provider.title()}: no models were returned.")
                continue
            index = names.index(default) if default in names else 0
            choice = st.sidebar.selectbox(f"{provider.title()} model", names, index=index,
                                          key=f"model_{provider}")
            router.set_model(provider, choice)
        if len(router.keys) > 1:
            router.primary = st.sidebar.radio("Try first", list(router.keys),
                                              format_func=str.title, key="primary_provider")
    st.sidebar.caption("Use the Chat tab to edit the BOQ in plain words. Keys are only needed for the chat.")
    return uploaded


# ----------------------------------------------------------------- loading
def load_pdf(uploaded):
    file_id = (uploaded.name, uploaded.size)
    if st.session_state.file_id == file_id:
        return
    data = uploaded.getvalue()
    path = None
    try:
        with st.spinner("Reading the tender and finding BOQ tables (a long tender can take a minute)..."):
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                f.write(data)
                path = f.name
            result = parse_boq(path)
    except Exception as e:                                    # show the problem instead of crashing
        st.error(f"Could not read this PDF: {e}")
        return
    finally:
        if path:
            Path(path).unlink(missing_ok=True)
    st.session_state.update(
        result=result, sessions=[EditSession(t) for t in result.tables], file_id=file_id,
        file_name=uploaded.name, pdf_bytes=data, plan=None, plan_table=None,
        chat=[], chat_plan=None)


# ----------------------------------------------------------------- tabs
def boq_tab(table):
    df = items_frame(table)
    st.dataframe(df, hide_index=True, column_config={
        "Description": st.column_config.TextColumn("Description", width="large"),
        "Quantity": st.column_config.NumberColumn("Quantity", format="%.2f"),
        "Original Rate": st.column_config.NumberColumn("Original Rate", format="%.2f"),
        "Rate": st.column_config.NumberColumn("Rate", format="%.2f"),
        "Amount": st.column_config.NumberColumn("Amount", format="%.2f")})
    st.caption("\u26a0 = this row needs review (see the next tab). 'Original Rate' is the rate printed "
               "in the tender; 'Rate' is the one you can change.")


def review_tab(table):
    for w in table.warnings:
        st.warning(w)
    df = review_frame(table)
    if df.empty:
        st.success("No rows need review in this table.")
    else:
        st.write("Check these rows against the PDF page shown:")
        st.dataframe(df, hide_index=True, column_config={
            "Problem": st.column_config.TextColumn("Problem", width="large")})


def verification_tab(table, session):
    v = table.verification()
    sections = len([r for r in table.rows if r.kind == "section"])
    a, b, c, d = st.columns(4)
    a.metric("Items found", len(table.items))
    b.metric("Sections", sections)
    c.metric("Sum of the rows now", fmt(v["sum_of_rows"]))
    d.metric("Total printed in the PDF", fmt(v["printed_total"]))
    if v["status"] == "match":
        st.success(v["reason"])
    elif v["status"] == "mismatch":
        st.error(v["reason"])
    else:
        st.info(v["reason"])
    if session.history:
        st.caption("You have edited rates, so the sum is expected to differ from the printed total.")
    if table.rates_blank:
        st.info("The rates in this tender are blank. Use the 'Edit rates' tab (Set rate) or fill "
                "them in the Excel file; Amount calculates itself there.")
    if table.totals:
        st.write("Totals printed in the PDF:")
        st.dataframe(pd.DataFrame([{"Label": t["label"], "Value": fmt(t["value"]), "PDF page": t["page"]}
                                   for t in table.totals]), hide_index=True)


def edit_tab(table, session, idx):
    st.write("Name the rows to change. Rows you do not name are never touched. You can name rows "
             "in more than one way at once.")
    c1, c2, c3 = st.columns(3)
    numbers = c1.text_input("Sr. Nos", placeholder="3, 5, 10-12", key=f"nums_{idx}")
    refs = c2.text_input("Ref / Item Nos", placeholder="7-198", key=f"refs_{idx}")
    words = c3.text_input("Words in the description", placeholder="door; aluminium", key=f"words_{idx}")
    all_words = st.checkbox("The description must contain ALL these words", key=f"all_{idx}")
    d1, d2 = st.columns(2)
    operation = d1.selectbox("Edit", OPERATIONS, key=f"op_{idx}")
    value = d2.text_input("Value", placeholder="10", key=f"val_{idx}")

    if st.button("Preview", key=f"preview_{idx}"):
        try:
            selector = Selector.from_spec(numbers=numbers, item_nos=refs, keywords=words,
                                          keywords_all=all_words)
            st.session_state.plan = session.plan(build_command(operation, value, selector))
            st.session_state.plan_table = idx
        except ValueError as e:
            st.session_state.plan = None
            st.error(str(e))

    plan = st.session_state.plan if st.session_state.plan_table == idx else None
    if plan is not None:
        st.subheader("Preview - nothing has been changed yet")
        st.write(f"**{plan.command.label()}** on {len(plan.changes)} row(s)")
        if plan.changes:
            st.dataframe(pd.DataFrame([{
                "Sr. No": c.sr_no, "Item No": c.item_no, "Description": c.description[:70],
                "Old": show_value(c.old), "New": show_value(c.new), "PDF page": c.page}
                for c in plan.changes]), hide_index=True)
            if plan.command.field in NUMERIC_FIELDS:
                st.metric("Effect on the BOQ total", f"{plan.amount_impact():+,.2f}")
        for c in plan.skipped:
            st.warning(f"Sr. No {c.sr_no} was named but NOT changed: {c.skip_reason}")
        for m in plan.not_found:
            st.warning(m)
        a, b = st.columns(2)
        if a.button("Apply these changes", disabled=not plan.changes, key=f"apply_{idx}"):
            try:
                n = session.apply(plan)
                st.session_state.message = f"Done: {plan.command.label()} on {n} row(s)."
                st.session_state.plan = None
                st.rerun()
            except StalePlanError as e:
                st.error(str(e))
        if b.button("Cancel", key=f"cancel_{idx}"):
            st.session_state.plan = None
            st.rerun()

    if session.history:
        st.divider()
        last = session.history[-1]
        st.write(f"Edits made so far: {len(session.history)}. Last one: {last['label']} "
                 f"({last['rows']} row(s)).")
        if st.button("Undo the last edit", key=f"undo_{idx}"):
            st.session_state.message = f"Undone: {session.undo()}"
            st.session_state.plan = None
            st.rerun()


# ----------------------------------------------------------------- main page
def main():
    uploaded = sidebar()
    st.title("Bidding Helper AI")
    st.caption("Upload a tender PDF, check the BOQ, edit rates and download the Excel file. "
               "Always check the results against the PDF before bidding.")
    if uploaded is not None:
        load_pdf(uploaded)
    if st.session_state.message:
        st.success(st.session_state.message)
        st.session_state.message = None

    result = st.session_state.result
    if result is None:
        st.info("Upload a tender PDF in the sidebar to begin.")
        return
    for w in result.warnings:
        st.warning(w)
    if not result.tables:
        st.error("No BOQ table was found in this PDF.")
        return

    tables, sessions = result.tables, st.session_state.sessions
    idx = 0
    if len(tables) > 1:
        idx = st.selectbox("BOQ table in this tender", list(range(len(tables))),
                           format_func=lambda i: f"{i + 1}. {tables[i].job} ({len(tables[i].items)} items)")
    table, session = tables[idx], sessions[idx]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Items", len(table.items))
    m2.metric("Need review", len(table.review_rows))
    m3.metric("BOQ tables in this PDF", len(tables))
    m4.metric("PDF pages with this table", len(table.pages))
    stem = Path(st.session_state.file_name).stem or "tender"
    st.download_button("Download Excel (.xlsx)", data=boq_excel_bytes(result, st.session_state.file_name),
                       file_name=f"{stem}_BOQ.xlsx", mime=XLSX)

    t0, t1, t2, t3, t4 = st.tabs(["Chat", "BOQ", f"Needs review ({len(table.review_rows)})",
                                  "Verification", "Edit rates"])
    with t0:
        chat_tab(table, session, idx, st.session_state.router, st.session_state.file_name)
    with t1:
        boq_tab(table)
    with t2:
        review_tab(table)
    with t3:
        verification_tab(table, session)
    with t4:
        edit_tab(table, session, idx)


main()
