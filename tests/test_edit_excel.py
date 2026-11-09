"""The Excel file must keep the tender's rate in 'Original Rate' after an edit."""
from pathlib import Path

from core.boq_edit import EditCommand, EditSession, Selector
from core.boq_parser import parse_boq
from core.excel_export import HEADER_ROW, build_boq_workbook

FIX = Path(__file__).parent / "fixtures"


def rows_by_sr(ws):
    return {ws.cell(r, 1).value: r for r in range(HEADER_ROW + 1, ws.max_row + 1)
            if str(ws.cell(r, 8).value or "").startswith("=IF(")}


def test_excel_keeps_original_rate_after_edit():
    result = parse_boq(FIX / "tender_a_nust_boq.pdf")
    t = result.tables[0]
    before = {r.sr_no: r.rate for r in t.items}
    s = EditSession(t)
    s.apply(s.plan(EditCommand("percent", 10, Selector.from_spec(numbers="3, 5"))))
    ws = build_boq_workbook(result, "x.pdf")["BOQ"]
    rows = rows_by_sr(ws)
    for sr in (3, 5):
        assert ws.cell(rows[sr], 6).value == before[sr]                   # Original Rate untouched
        assert ws.cell(rows[sr], 7).value == round(before[sr] * 1.1, 2)   # Rate changed
    r4 = rows[4]                                                          # a row nobody edited
    assert ws.cell(r4, 6).value == ws.cell(r4, 7).value == before[4]


def test_original_rate_stays_blank_when_a_rate_is_set_on_a_blank_row():
    result = parse_boq(FIX / "tender_b_jiap_boq.pdf")
    s = EditSession(result.tables[0])
    s.apply(s.plan(EditCommand("set", 1000, Selector.from_spec(numbers="1"))))
    ws = build_boq_workbook(result, "x.pdf")["BOQ"]
    r = rows_by_sr(ws)[1]
    assert ws.cell(r, 6).value is None and ws.cell(r, 7).value == 1000
