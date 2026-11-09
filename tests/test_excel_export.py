"""Phase 2 tests: the Excel export."""
from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import load_workbook

from core.boq_parser import ParseResult, parse_boq
from core.excel_export import HEADER_ROW, HEADERS, boq_excel_bytes, build_boq_workbook

FIX = Path(__file__).parent / "fixtures"


def build(name):
    result = parse_boq(FIX / f"{name}.pdf")
    return result, build_boq_workbook(result, f"{name}.pdf")


def item_rows(ws):
    """Rows holding a BOQ item (their Amount cell is the =IF(...) formula)."""
    return [r for r in range(HEADER_ROW + 1, ws.max_row + 1)
            if str(ws.cell(r, 8).value or "").startswith("=IF(")]


def test_sheet_names():
    assert build("tender_a_nust_boq")[1].sheetnames == ["BOQ", "Summary"]
    assert build("tender_b_jiap_boq")[1].sheetnames == ["BOQ", "Summary"]
    assert build("tender_c_pidcl_boq")[1].sheetnames == ["BOQ 1", "BOQ 2", "Summary"]


def test_header_row_and_frozen_panes():
    ws = build("tender_a_nust_boq")[1]["BOQ"]
    assert [ws.cell(HEADER_ROW, c).value for c in range(1, 11)] == HEADERS
    assert ws.freeze_panes == "A5"


@pytest.mark.parametrize("name,count", [("tender_a_nust_boq", 42), ("tender_b_jiap_boq", 5)])
def test_one_row_per_item(name, count):
    result, wb = build(name)
    assert len(item_rows(wb["BOQ"])) == count == len(result.tables[0].items)


def test_numbers_match_parser_and_printed_total_for_tender_a():
    result, wb = build("tender_a_nust_boq")
    ws = wb["BOQ"]
    total = 0.0
    for r, item in zip(item_rows(ws), result.tables[0].items):
        assert ws.cell(r, 5).value == item.quantity
        assert ws.cell(r, 6).value == item.rate == ws.cell(r, 7).value  # original rate kept
        total += ws.cell(r, 5).value * ws.cell(r, 7).value
    assert total == pytest.approx(8847343.79, abs=1.0)


def test_blank_rates_stay_blank_in_tender_b():
    ws = build("tender_b_jiap_boq")[1]["BOQ"]
    r = item_rows(ws)[0]
    assert ws.cell(r, 6).value is None and ws.cell(r, 7).value is None
    assert ws.cell(r, 8).value == f'=IF(OR(E{r}="",G{r}=""),"",E{r}*G{r})'


def test_review_row_is_highlighted_and_explained():
    ws = build("tender_a_nust_boq")[1]["BOQ"]
    row24 = next(r for r in item_rows(ws) if ws.cell(r, 1).value == 24)
    assert ws.cell(row24, 10).value
    assert ws.cell(row24, 1).fill.fgColor.rgb.endswith("FFF2CC")


def test_sections_subtotals_and_grand_total_formulas():
    ws = build("tender_a_nust_boq")[1]["BOQ"]
    values = [str(ws.cell(r, 8).value or "") for r in range(HEADER_ROW + 1, ws.max_row + 1)]
    assert sum(v.startswith("=SUM(H") and ":" in v for v in values) == 3   # three subtotals
    assert any(v.startswith("=SUM(H") and "," in v for v in values)         # grand total
    assert any(ws.cell(r, 3).value == "GRAND TOTAL" for r in range(1, ws.max_row + 1))


def test_summary_points_at_boq_sheet():
    wb = build("tender_a_nust_boq")[1]
    text = " ".join(str(c.value) for row in wb["Summary"].iter_rows()
                    for c in row if c.value is not None)
    assert "'BOQ'!H" in text and "Grand total" in text


def test_excel_bytes_open_again():
    data = boq_excel_bytes(parse_boq(FIX / "tender_b_jiap_boq.pdf"), "x.pdf")
    assert data[:2] == b"PK"
    assert load_workbook(BytesIO(data)).sheetnames == ["BOQ", "Summary"]


def test_no_tables_raises():
    with pytest.raises(ValueError):
        build_boq_workbook(ParseResult())
