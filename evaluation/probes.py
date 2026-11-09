"""Stress probes: small made-up tables that test one tricky situation each.

Each probe returns True when the parser behaves correctly. They are used both by
the evaluation report and by the automatic tests.
"""
from core.boq_parser import parse_boq_tables, parse_number

H = ["Sr. No", "Ref No.", "Description", "Unit", "Quantity", "Rate", "Amount"]


def _run(*tables_per_page, texts=None):
    pages = []
    for i, tables in enumerate(tables_per_page, start=1):
        text = (texts or {}).get(i, "")
        pages.append({"page": i, "text": text, "tables": tables})
    return parse_boq_tables(pages)


def probe_row_split_across_pages():
    r = _run([[H, ["1", "A-1", "Fix door", "Nos", "2", "100", "200"]]],
             [[H, ["", "", "and paint it", "", "", "", ""],
               ["2", "A-2", "Window", "Nos", "1", "50", "50"]]])
    t = r.tables[0]
    first = t.items[0]
    return (len(t.items) == 2 and "and paint it" in first.description
            and any(f["code"] == "joined_across_pages" for f in first.flags))


def probe_missing_row_number():
    r = _run([[H, ["1", "a", "x", "Nos", "1", "1", "1"], ["2", "b", "y", "Nos", "1", "1", "1"],
               ["4", "d", "z", "Nos", "1", "1", "1"]]])
    t = r.tables[0]
    return any("jumps" in w for w in t.warnings) and t.items[2].needs_review


def probe_unreadable_quantity():
    r = _run([[H, ["1", "a", "x", "Nos", "as per note", "10", ""]]])
    return any(f["code"] == "quantity_unreadable" for f in r.tables[0].items[0].flags)


def probe_amount_mismatch():
    r = _run([[H, ["1", "a", "x", "Nos", "10", "5", "80"]]])
    return any(f["code"] == "amount_mismatch" for f in r.tables[0].items[0].flags)


def probe_repeated_header_row_ignored():
    r = _run([[H, ["1", "a", "x", "Nos", "1", "1", "1"], H, ["2", "b", "y", "Nos", "1", "1", "1"]]])
    return len(r.tables[0].items) == 2


def probe_footer_text_mixed_into_row():
    header9 = ["cqu", "Sr. No", "Ref No.", "Description", "Unit", "Quantity", "Rate", "Amount", "e 51"]
    row7 = ["3 isition and Dispo", "MR ADS) generated document | \u00a9 20", "Sealing", "Sqm",
            "45", "2304.79", "103715.55 Pag"]
    r = _run([[header9, row7]])
    it = r.tables[0].items[0]
    return (it.sr_no == 3 and it.amount == 103715.55 and it.item_no == "MR"
            and any(f["code"] == "footer_noise" for f in it.flags))


def probe_unit_inside_quantity():
    r = _run([[H, ["1", "1", "x", "P.Sft", "432 Sft", "", "-"],
               ["2", "2", "y", "", "10 Sft", "", "-"]]])
    a, b = r.tables[0].items
    return a.quantity == 432 and a.unit == "P.Sft" and b.quantity == 10 and b.unit == "Sft"


def probe_other_column_spellings():
    h = ["S.No.", "Description", "Unit", "Qty.", "Rate (PKR)", "Amount (PKR)"]
    r = _run([[["BILL OF QUANTITIES (BOQ)", "", "", "", "", ""], h,
               ["1", "Panels", "Nos.", "70", "", ""]]])
    t = r.tables[0]
    return t.job == "BILL OF QUANTITIES (BOQ)" and t.items[0].sr_no == 1 and t.items[0].quantity == 70


def probe_total_row_not_an_item():
    r = _run([[H, ["1", "a", "x", "Nos", "1", "5", "5"], ["2", "Total", "", "", "", "", "5"],
               ["", "", "", "", "", "GRAND TOTAL:", "Rs5.00"]]])
    t = r.tables[0]
    return len(t.items) == 1 and t.printed_total() == 5 and t.verification()["status"] == "match"


def probe_page_without_header():
    r = _run([[H, ["1", "a", "x", "Nos", "1", "1", "1"]]],
             [[["2", "b", "y", "Nos", "1", "1", "1"]]])
    t = r.tables[0]
    return len(t.items) == 2 and any("no header" in w for w in t.warnings)


def probe_non_boq_table_ignored():
    r = _run([[["Name", "Age"], ["a", "b"]]])
    return r.tables == []


def probe_two_jobs_two_tables():
    r = _run([[H, ["1", "a", "x", "Nos", "1", "1", "1"]]], [[H, ["1", "a", "x", "Nos", "1", "1", "1"]]],
             texts={1: "Job: Civil works", 2: "Job: Electrical works"})
    return [t.job for t in r.tables] == ["Civil works", "Electrical works"]


def probe_number_reading():
    return (parse_number("1,234.50") == (1234.5, "") and parse_number("-") == (None, "")
            and parse_number("Rs8,847,343.79") == (8847343.79, "")
            and parse_number("432 Sft") == (432.0, "Sft") and parse_number("") == (None, ""))


PROBES = {
    "Row description split across two pages is joined and flagged": probe_row_split_across_pages,
    "Missing row number is reported": probe_missing_row_number,
    "Unreadable quantity is flagged": probe_unreadable_quantity,
    "Amount that differs from quantity x rate is flagged": probe_amount_mismatch,
    "Repeated header row inside a table is ignored": probe_repeated_header_row_ignored,
    "Page footer text mixed into a row is cleaned and flagged": probe_footer_text_mixed_into_row,
    "Unit written inside the quantity cell ('432 Sft')": probe_unit_inside_quantity,
    "Other column spellings (S.No., Qty., Rate (PKR))": probe_other_column_spellings,
    "Total rows are not counted as items": probe_total_row_not_an_item,
    "Table continued on a page without a header row": probe_page_without_header,
    "Tables that are not a BOQ are ignored": probe_non_boq_table_ignored,
    "Two jobs in one tender give two separate tables": probe_two_jobs_two_tables,
    "Numbers like 1,234.50, Rs8,847,343.79 and '-' are read correctly": probe_number_reading,
}
