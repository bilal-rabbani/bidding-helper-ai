"""Builds the downloadable Excel file from parsed BOQ tables.

Sheets:
  BOQ  (or "BOQ 1", "BOQ 2" ... when a tender has several BOQ tables)
       section headings, live Amount formulas, section subtotals, grand total
  Summary
       section totals and a check against the total printed in the PDF
"""
import io
import math

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.properties import PageSetupProperties

from core.settings import load_settings
from core.urdu import urdu_check_for, urdu_for

HEADERS = ["Sr. No", "Item No", "Description", "Unit", "Quantity",
           "Original Rate", "Rate", "Amount", "PDF page", "Review note"]
WIDTHS = [7, 14, 70, 9, 12, 14, 14, 16, 9, 42]
HEADER_ROW = 4
FIRST_DATA_ROW = 5
LAST_COL = len(HEADERS)
NUMBER_FORMAT = "#,##0.00"

_thin = Side(style="thin", color="BFBFBF")
BORDER = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)
TOTAL_BORDER = Border(left=_thin, right=_thin, bottom=_thin,
                      top=Side(style="medium", color="000000"))
FILL_HEADER = PatternFill("solid", fgColor="1F3864")
FILL_SECTION = PatternFill("solid", fgColor="D9E1F2")
FILL_SUBTOTAL = PatternFill("solid", fgColor="F2F2F2")
FILL_REVIEW = PatternFill("solid", fgColor="FFF2CC")
FILL_GRAND = PatternFill("solid", fgColor="E2EFDA")


def _font(bold=False, italic=False, size=10, color=None):
    return Font(name="Calibri", size=size, bold=bold, italic=italic, color=color)


def _style_row(ws, r, fill=None, bold=False, border=BORDER):
    for c in range(1, LAST_COL + 1):
        cell = ws.cell(r, c)
        cell.font = _font(bold=bold)
        cell.border = border
        if fill is not None:
            cell.fill = fill
        cell.alignment = Alignment(vertical="top", wrap_text=c in (3, 10))
    for c in (5, 6, 7, 8):
        ws.cell(r, c).number_format = NUMBER_FORMAT
    ws.cell(r, 1).alignment = Alignment(horizontal="center", vertical="top")


def _write_header(ws):
    for c, (text, width) in enumerate(zip(HEADERS, WIDTHS), start=1):
        cell = ws.cell(HEADER_ROW, c, text)
        cell.font = _font(bold=True, color="FFFFFF")
        cell.fill = FILL_HEADER
        cell.border = BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(c)].width = width


def _set_height(ws, r, text):
    lines = max(1, math.ceil(len(text or "") / 78))
    if lines > 1:
        ws.row_dimensions[r].height = min(400, 13 * lines + 2)


def _write_item(ws, r, row):
    original = getattr(row, "original_rate", row.rate)   # blank stays blank
    note = "; ".join(f["message"] for f in row.flags)
    values = [row.sr_no, row.item_no, row.description, row.unit, row.quantity,
              original, row.rate, None, row.page, note]
    _style_row(ws, r, FILL_REVIEW if row.needs_review else None)
    for c, v in enumerate(values, start=1):
        if v is not None and v != "":
            ws.cell(r, c, v)
    ws.cell(r, 8, f'=IF(OR(E{r}="",G{r}=""),"",E{r}*G{r})')
    _set_height(ws, r, row.description)


def _write_note(ws, r, row):
    _style_row(ws, r)
    ws.cell(r, 1, row.sr_no)
    ws.cell(r, 2, row.item_no)
    ws.cell(r, 3, row.description)
    for c in range(1, LAST_COL + 1):
        ws.cell(r, c).font = _font(italic=True)
    _set_height(ws, r, row.description)


def _write_boq_sheet(ws, table, source_name):
    ws["A1"] = f"Bill of Quantities - {table.job}"
    ws["A1"].font = _font(bold=True, size=14)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=LAST_COL)
    ws["A2"] = (f"Source: {source_name}. 'PDF page' is the page number in that file. "
                "Yellow rows need review.")
    ws["A2"].font = _font(italic=True, color="595959")
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=LAST_COL)
    _write_header(ws)

    r = FIRST_DATA_ROW
    has_sections = any(x.kind == "section" for x in table.rows)
    groups, state = [], {"current": None}
    n_items = n_review = 0
    first_item = last_item = None

    def close_group():
        nonlocal r
        g = state["current"]
        state["current"] = None
        if g is None or g["first"] is None:
            return
        _style_row(ws, r, FILL_SUBTOTAL, bold=True)
        ws.cell(r, 3, f"Subtotal - {g['name']}")
        ws.cell(r, 8, f"=SUM(H{g['first']}:H{g['last']})")
        g["sub_row"] = r
        groups.append(g)
        r += 1

    for row in table.rows:
        if row.kind == "total":
            continue
        if row.kind == "section":
            close_group()
            _style_row(ws, r, FILL_SECTION, bold=True)
            ws.cell(r, 1, row.description)
            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=LAST_COL)
            ws.cell(r, 1).alignment = Alignment(horizontal="left", vertical="center")
            state["current"] = {"name": row.description, "items": 0, "first": None, "last": None}
            r += 1
            continue
        if row.kind == "note":
            _write_note(ws, r, row)
            r += 1
            continue
        if has_sections and state["current"] is None:
            state["current"] = {"name": "(before the first section)",
                                "items": 0, "first": None, "last": None}
        _write_item(ws, r, row)
        g = state["current"]
        if g is not None:
            g["first"] = g["first"] or r
            g["last"] = r
            g["items"] += int(row.kind == "item")
        first_item = first_item or r
        last_item = r
        n_items += int(row.kind == "item")
        n_review += int(row.needs_review)
        r += 1
    close_group()

    r += 1
    if groups:
        formula = "=SUM(" + ",".join(f"H{g['sub_row']}" for g in groups) + ")"
    elif first_item:
        formula = f"=SUM(H{first_item}:H{last_item})"
    else:
        formula = "=0"
    _style_row(ws, r, FILL_GRAND, bold=True, border=TOTAL_BORDER)
    ws.cell(r, 3, "GRAND TOTAL")
    ws.cell(r, 8, formula)

    ws.freeze_panes = "A5"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.print_title_rows = f"{HEADER_ROW}:{HEADER_ROW}"
    return {"groups": groups, "grand_row": r, "n_items": n_items, "n_review": n_review}


def _write_summary(ws, tables, infos, names, source_name):
    for col, width in zip("ABCD", (46, 14, 22, 30)):
        ws.column_dimensions[col].width = width
    ws["A1"] = "Bidding Helper AI - BOQ summary"
    ws["A1"].font = _font(bold=True, size=14)
    ws["A2"] = f"Source: {source_name}"
    ws["A3"] = "Check every figure against the tender PDF before bidding."
    ws["A3"].font = _font(italic=True, color="C00000")
    r = 5
    for table, info, sheet in zip(tables, infos, names):
        ref = f"'{sheet}'!"
        for c in range(1, 4):
            ws.cell(r, c).fill = FILL_SECTION
            ws.cell(r, c).font = _font(bold=True)
        ws.cell(r, 1, f"Job: {table.job}")
        r += 1
        for c, text in enumerate(["Section", "Items", "Amount (PKR)"], start=1):
            cell = ws.cell(r, c, text)
            cell.font = _font(bold=True, color="FFFFFF")
            cell.fill = FILL_HEADER
            cell.border = BORDER
        r += 1
        start = r
        groups = info["groups"] or [{"name": "All items", "items": info["n_items"],
                                     "sub_row": info["grand_row"]}]
        for g in groups:
            ws.cell(r, 1, g["name"])
            ws.cell(r, 2, g["items"])
            ws.cell(r, 3, f"={ref}H{g['sub_row']}")
            for c in range(1, 4):
                ws.cell(r, c).border = BORDER
                ws.cell(r, c).font = _font()
            ws.cell(r, 3).number_format = NUMBER_FORMAT
            r += 1
        ws.cell(r, 1, "Grand total")
        ws.cell(r, 2, f"=SUM(B{start}:B{r - 1})")
        ws.cell(r, 3, f"={ref}H{info['grand_row']}")
        for c in range(1, 4):
            ws.cell(r, c).border = TOTAL_BORDER
            ws.cell(r, c).fill = FILL_GRAND
            ws.cell(r, c).font = _font(bold=True)
        ws.cell(r, 3).number_format = NUMBER_FORMAT
        sum_row = r
        r += 2

        v = table.verification()
        printed = v["printed_total"]
        ws.cell(r, 1, "Rows extracted")
        ws.cell(r, 3, info["n_items"])
        r += 1
        ws.cell(r, 1, "Rows needing review (yellow on the BOQ sheet)")
        ws.cell(r, 3, info["n_review"])
        r += 1
        ws.cell(r, 1, "Total printed in the PDF")
        ws.cell(r, 3, printed if printed is not None else "not printed")
        ws.cell(r, 3).number_format = NUMBER_FORMAT
        printed_row = r
        r += 1
        ws.cell(r, 1, "Sum of rows now")
        ws.cell(r, 3, f"=C{sum_row}")
        ws.cell(r, 3).number_format = NUMBER_FORMAT
        r += 1
        ws.cell(r, 1, "Difference now (sum minus printed)")
        if table.rates_blank:
            ws.cell(r, 3, "n/a (rates are blank)")
        else:
            ws.cell(r, 3, f'=IF(ISNUMBER(C{printed_row}),C{r - 1}-C{printed_row},"")')
            ws.cell(r, 3).number_format = NUMBER_FORMAT
        r += 1
        ws.cell(r, 1, "Check when exported")
        ws.cell(r, 2, v["reason"])
        ws.cell(r, 2).alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=4)
        ws.row_dimensions[r].height = 32
        for rr in range(r - 5, r + 1):
            ws.cell(rr, 1).font = _font()
        r += 3


URDU_HEADERS = ["Sr. No", "Item No", "Description (English)", "Description (Urdu)", "Unit", "Quantity", "Check"]
URDU_WIDTHS = [7, 14, 55, 55, 9, 12, 38]


def _write_urdu_sheet(ws, table, source_name):
    """English and Urdu descriptions side by side; the Urdu is right-aligned and reads right to left."""
    font_name = (load_settings().get("urdu") or {}).get("excel_font") or "Urdu Typesetting"
    ws["A1"] = f"Item descriptions in Urdu - {table.job}"
    ws["A1"].font = _font(bold=True, size=14)
    ws["A2"] = f"Translated by AI - please check. Yellow rows have a note. Source: {source_name}"
    ws["A2"].font = _font(italic=True, color="595959")
    for c, (text, width) in enumerate(zip(URDU_HEADERS, URDU_WIDTHS), start=1):
        cell = ws.cell(HEADER_ROW, c, text)
        cell.font = _font(bold=True, color="FFFFFF")
        cell.fill = FILL_HEADER
        cell.border = BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(c)].width = width
    r = FIRST_DATA_ROW
    for row in table.items:
        urdu = urdu_for(row)
        if not urdu:
            continue
        check = urdu_check_for(row)
        values = [row.sr_no, row.item_no, row.description, urdu, row.unit, row.quantity, check]
        for c, v in enumerate(values, start=1):
            cell = ws.cell(r, c, v if v not in ("", None) else None)
            cell.border = BORDER
            cell.font = _font()
            cell.alignment = Alignment(vertical="top", wrap_text=c in (3, 4, 7))
            if check:
                cell.fill = FILL_REVIEW
        ws.cell(r, 1).alignment = Alignment(horizontal="center", vertical="top")
        ws.cell(r, 6).number_format = NUMBER_FORMAT
        ws.cell(r, 4).font = Font(name=font_name, size=14)
        ws.cell(r, 4).alignment = Alignment(horizontal="right", vertical="top", wrap_text=True, readingOrder=2)
        lines = max(1, math.ceil(len(row.description) / 55), math.ceil(len(urdu) / 32))
        ws.row_dimensions[r].height = min(400, 24 * lines)
        r += 1
    ws.freeze_panes = "A5"


def build_boq_workbook(result, source_name="tender.pdf"):
    """Return an openpyxl Workbook for a ParseResult."""
    if not result.tables:
        raise ValueError("No BOQ table was found, so there is nothing to export.")
    wb = Workbook()
    names, infos = [], []
    for i, table in enumerate(result.tables, start=1):
        title = "BOQ" if len(result.tables) == 1 else f"BOQ {i}"
        ws = wb.active if i == 1 else wb.create_sheet()
        ws.title = title
        infos.append(_write_boq_sheet(ws, table, source_name))
        names.append(title)
        if any(urdu_for(r) for r in table.items):
            _write_urdu_sheet(wb.create_sheet(f"{title} Urdu"), table, source_name)
    _write_summary(wb.create_sheet("Summary"), result.tables, infos, names, source_name)
    return wb


def save_boq_excel(result, path, source_name=None):
    build_boq_workbook(result, source_name or "tender.pdf").save(path)
    return path


def boq_excel_bytes(result, source_name="tender.pdf"):
    """The Excel file as bytes, for a download button in the app."""
    buf = io.BytesIO()
    build_boq_workbook(result, source_name).save(buf)
    return buf.getvalue()
