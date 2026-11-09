"""One-time helper: draft the "right answers" (gold data) for the test tenders.

It reads each PDF a SECOND, independent way (the plain text layout from
`pdftotext -layout`, not the table finder the parser uses) so that mistakes in
one method show up as disagreements with the other. The draft is then checked
by a person (see evaluation/gold/SPOT_CHECK.md). Needs poppler-utils.

Run:  python evaluation/make_gold_draft.py
"""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures"
OUT = ROOT / "evaluation" / "gold"


def layout_lines(pdf: Path) -> list:
    text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                          capture_output=True, text=True, check=True).stdout
    return text.splitlines()


def num(s):
    if s is None:
        return None
    s = re.sub(r"^rs\.?\s*", "", s.strip(), flags=re.I)
    m = re.match(r"-?\d[\d,]*(?:\.\d+)?", s)
    return float(m.group().replace(",", "")) if m else None


def split_tokens(line: str) -> list:
    return re.split(r"\s{2,}", line.strip())


def items_from_first_lines(lines, layout):
    """Rows whose first printed line carries every column (tenders A, B, C main)."""
    rows, sections, notes = [], [], []
    for line in lines:
        if not re.match(r"^\s*\d+\s{2,}\S", line):
            continue
        t = split_tokens(line)
        if any(x.lower().startswith("total") or "TOTAL" in x for x in t):
            continue
        if layout == "A":
            if len(t) == 3 and t[1].lower() == "note":
                notes.append(t[0]); continue
            if len(t) == 3:
                sections.append(f"{t[1]} {t[2]}"); continue
            sr, ref, _, unit, qty, rate, amt = t[:7]
            rows.append(dict(sr_no=int(sr), item_no=ref, unit=unit, quantity=num(qty),
                             rate=num(rate), amount=num(amt)))
        elif layout == "B":
            sr, sno, _, unit, qty, amt = t[:6]
            rows.append(dict(sr_no=int(sr), item_no=sno, unit=unit, quantity=num(qty),
                             rate=None, amount=num(amt)))
        elif layout == "C":
            if len(t) != 5:
                continue
            sr, sno, _, unit, qty = t
            rows.append(dict(sr_no=int(sr), item_no=sno, unit=unit, quantity=num(qty),
                             rate=None, amount=None))
    return rows, sections


def annex_rows(lines):
    """Annexure BOQ: number and title on one line, unit and quantity on a later line."""
    rows, cur = [], None
    for line in lines:
        m = re.match(r"^\s*(\d+)\s{2,}[A-Z]", line)
        if m:
            cur = int(m.group(1))
            continue
        m = re.search(r"\s{2,}([A-Za-z.]+)\s{2,}([\d.,]+)\s*$", line)
        if cur is not None and m:
            rows.append(dict(sr_no=cur, item_no="", unit=m.group(1), quantity=num(m.group(2)),
                             rate=None, amount=None))
            cur = None
    return rows


def printed_total(lines):
    """The amount printed after 'GRAND TOTAL:' (the words may wrap over two lines)."""
    m = re.search(r"GRAND\s+(?:TOTAL:?\s+)?Rs\.?\s*([\d,]+(?:\.\d+)?)", "\n".join(lines))
    return num(m.group(1)) if m else None


def main():
    # tender A
    a_lines = layout_lines(FIX / "tender_a_nust_boq.pdf")
    a_rows, _ = items_from_first_lines(a_lines, "A")
    # Section names wrap over two lines in the layout text, so they are typed
    # here from the PDF (A, B and C headings on pages 1, 13 and 21 of the excerpt).
    a_sections = ["A. CIVIL Works", "B. ELECTRICAL Works", "C. HVAC Works"]
    # tender B
    b_lines = layout_lines(FIX / "tender_b_jiap_boq.pdf")
    b_rows, _ = items_from_first_lines(b_lines, "B")
    # tender C: main table on the first three pages, annexure on the last page
    c_lines = layout_lines(FIX / "tender_c_pidcl_boq.pdf")
    split_at = next(i for i, l in enumerate(c_lines) if "BILL OF QUANTITIES" in l)
    c_main, _ = items_from_first_lines(c_lines[:split_at], "C")
    c_annex = annex_rows(c_lines[split_at:])

    gold = {
        "tender_a_nust_boq.pdf": {"tables": [{
            "name": "NUST C3A offices", "expected_sections": a_sections,
            "printed_total": printed_total(a_lines), "expected_verification": "match",
            "rows": a_rows}]},
        "tender_b_jiap_boq.pdf": {"tables": [{
            "name": "JIAP public address rooms", "expected_sections": [],
            "printed_total": printed_total(b_lines), "expected_verification": "cannot_verify",
            "rows": b_rows}]},
        "tender_c_pidcl_boq.pdf": {"tables": [
            {"name": "PIDCL main table", "expected_sections": [],
             "printed_total": printed_total(c_lines[:split_at]),
             "expected_verification": "cannot_verify", "rows": c_main},
            {"name": "PIDCL annexure BOQ", "expected_sections": [],
             "printed_total": None, "expected_verification": "cannot_verify",
             "rows": c_annex}]},
    }
    for name, g in gold.items():
        g["status"] = "DRAFT - made by a second extraction method, to be spot-checked by a person"
        g["verified_by_person"] = False
        (OUT / (Path(name).stem + ".json")).write_text(json.dumps(g, indent=1), encoding="utf-8")
        print(name, [len(t["rows"]) for t in g["tables"]], "rows")


if __name__ == "__main__":
    main()
