"""Finds BOQ tables in an EPADS tender PDF and turns them into clean rows.

Plain code, no LLM. Anything uncertain gets a flag and is listed under
"needs review" instead of being guessed.

Main entry points:
    parse_boq(pdf_path)          -> ParseResult   (reads a PDF)
    parse_boq_tables(page_dicts) -> ParseResult   (same logic on ready-made tables,
                                                   used by the unit tests)
"""
import re
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

from core.settings import load_settings

FIELDS = ["sr_no", "item_no", "description", "unit", "quantity", "rate", "amount"]
NUMBER_FIELDS = ("quantity", "rate", "amount")

# Letters of the EPADS page footer. Footer text sometimes runs into the last
# table row of a page, and we use this to recognise and strip such fragments.
FOOTER_LETTERS = "epakacquisitionanddisposalsystemepadsgenerateddocumentpageof"


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def _clean(text) -> str:
    """Join lines and collapse spaces: 'Sr.\\nNo' -> 'Sr. No'."""
    return " ".join((text or "").split())


def _norm(text) -> str:
    """Lower case letters and digits only: 'Sr. No' -> 'srno'."""
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def parse_number(text):
    """Read a number at the start of a cell.

    Returns (value, leftover). value is None when there is no number.
    Examples: '1,234.50' -> (1234.5, '');  '432 Sft' -> (432.0, 'Sft');
    'Rs8,847,343.79' -> (8847343.79, '');  '-' -> (None, '').
    """
    t = (text or "").strip()
    if t in ("", "-", "\u2013", "\u2014"):
        return None, ""
    t = re.sub(r"^(rs\.?|pkr)\s*", "", t, flags=re.I)
    m = _NUMBER.match(t)
    if not m:
        return None, t
    return float(m.group().replace(",", "")), t[m.end():].strip()


def _flag(code: str, message: str) -> dict:
    return {"code": code, "message": message}


# --------------------------------------------------------------------------
# Data classes
# --------------------------------------------------------------------------
@dataclass
class BOQRow:
    kind: str                 # item | section | note | total | unknown
    page: int                 # page of the PDF the row was read from
    sr_no: object = None      # int or None
    item_no: str = ""         # Ref No. / S. No. column
    description: str = ""
    unit: str = ""
    quantity: object = None   # float or None
    quantity_raw: str = ""
    rate: object = None
    original_rate: object = None   # the rate printed in the tender; never changed
    amount: object = None
    section: str = ""
    flags: list = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return bool(self.flags)

    def effective_amount(self):
        """Printed amount, or quantity x rate when the amount is not printed."""
        if self.amount is not None:
            return self.amount
        if self.quantity is not None and self.rate is not None:
            return self.quantity * self.rate
        return None

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["needs_review"] = self.needs_review
        return d


@dataclass
class BOQTable:
    job: str
    pages: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    totals: list = field(default_factory=list)      # printed total rows
    warnings: list = field(default_factory=list)
    columns: list = field(default_factory=list)     # field names found in the header

    @property
    def items(self) -> list:
        return [r for r in self.rows if r.kind == "item"]

    @property
    def review_rows(self) -> list:
        return [r for r in self.rows if r.needs_review]

    @property
    def rates_blank(self) -> bool:
        items = self.items
        return bool(items) and all(r.rate is None for r in items)

    def sum_amount(self):
        values = [r.effective_amount() for r in self.items]
        values = [v for v in values if v is not None]
        return sum(values) if values else None

    def printed_total(self):
        """The printed grand total if there is one, else the last 'Total' row value."""
        for t in self.totals:
            if t["grand"] and t["value"] is not None:
                return t["value"]
        for t in reversed(self.totals):
            if t["value"] is not None:
                return t["value"]
        return None

    def verification(self, tolerance: float = 1.0) -> dict:
        """Compare the sum of the rows with the total printed in the PDF."""
        total = self.printed_total()
        s = self.sum_amount()
        if s is None:
            reason = ("Rates are blank, so the printed total cannot be checked against the rows."
                      if total is not None else
                      "Rates are blank and no total is printed.")
            status = "cannot_verify"
        elif total is None:
            status, reason = "cannot_verify", "No total is printed in this table."
        elif abs(s - total) <= tolerance:
            status, reason = "match", "Sum of the rows equals the printed total."
        else:
            status = "mismatch"
            reason = f"Sum of the rows is {s:,.2f} but the printed total is {total:,.2f}."
        return {"status": status, "reason": reason,
                "sum_of_rows": s, "printed_total": total}

    def to_dict(self) -> dict:
        return {
            "job": self.job,
            "pages": self.pages,
            "columns": self.columns,
            "items": len(self.items),
            "sections": len([r for r in self.rows if r.kind == "section"]),
            "needs_review": len(self.review_rows),
            "rates_blank": self.rates_blank,
            "verification": self.verification(),
            "warnings": self.warnings,
            "rows": [r.to_dict() for r in self.rows],
            "totals": self.totals,
        }


@dataclass
class ParseResult:
    tables: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    page_texts: list = field(default_factory=list)      # the text of every PDF page

    def to_dict(self) -> dict:
        return {"warnings": self.warnings, "tables": [t.to_dict() for t in self.tables]}


# --------------------------------------------------------------------------
# Header handling
# --------------------------------------------------------------------------
def _alias_lookup() -> dict:
    cols = load_settings()["boq_columns"]
    return {f: {_norm(a) for a in cols[f]} for f in FIELDS}


def _candidates(cell, aliases) -> list:
    n = _norm(cell)
    if not n:
        return []
    return [f for f in FIELDS if n in aliases[f]]


def _map_header(row, aliases) -> dict:
    """Return {column index: field name}. A name already used goes to the next candidate."""
    taken, mapping = set(), {}
    for ci, cell in enumerate(row):
        for f in _candidates(cell, aliases):
            if f not in taken:
                mapping[ci] = f
                taken.add(f)
                break
    return mapping


def _find_header(table, aliases):
    """Look in the first rows of a table for the header. Returns (row index, mapping) or None."""
    for idx, row in enumerate(table[:8]):
        mapping = _map_header(row, aliases)
        fields = set(mapping.values())
        if "description" in fields and len(fields & {"unit", "quantity", "rate", "amount"}) >= 2:
            return idx, mapping
    return None


# --------------------------------------------------------------------------
# Row handling
# --------------------------------------------------------------------------
def _align(row, header_len, mapping):
    """Match one data row to the header. Returns (values by field, aligned_ok)."""
    cols = sorted(mapping)
    first, last = cols[0], cols[-1]
    core_len = last - first + 1
    if len(row) == header_len:
        offset, ok = 0, True
    elif len(row) == core_len:
        offset, ok = -first, True          # header has extra outer columns
    else:
        offset, ok = 0, False              # shape differs: best effort, will be flagged
    values = {f: "" for f in FIELDS}
    for ci, f in mapping.items():
        j = ci + offset
        if 0 <= j < len(row):
            values[f] = _clean(row[j])
    return values, ok


def _is_footer_noise(word: str, previous: str) -> bool:
    letters = re.sub(r"[^a-z]", "", word.lower())
    if not re.search(r"[A-Za-z0-9]", word):
        return True                                   # symbols such as | or a copyright sign
    if len(letters) >= 3 and letters in FOOTER_LETTERS:
        return True                                   # a piece of the footer words
    return word.isdigit() and len(word) <= 4 and not re.search(r"[A-Za-z0-9]", previous)


def _strip_footer_words(text: str) -> str:
    """Remove trailing words that are fragments of the page footer."""
    words = text.split()
    while words and _is_footer_noise(words[-1], words[-2] if len(words) > 1 else ""):
        words.pop()
    return " ".join(words)


def _make_row(values, aligned, page, section):
    """Build a row. Returns (row, noisy) where noisy means footer text was mixed in."""
    flags = []
    # row number
    sr_text = values["sr_no"]
    sr_no, sr_left = None, ""
    m = re.match(r"^(\d+)\s*(.*)$", sr_text)
    if m:
        sr_no, sr_left = int(m.group(1)), m.group(2)
    contaminated = bool(sr_left)

    nums, lefts = {}, {}
    for f in NUMBER_FIELDS:
        nums[f], lefts[f] = parse_number(values[f])

    unit = values["unit"]
    # "432 Sft": the unit written inside the quantity cell
    if lefts["quantity"] and re.fullmatch(r"[A-Za-z.]+", lefts["quantity"]):
        if not unit:
            unit = lefts["quantity"]
        lefts["quantity"] = ""
    if lefts["rate"] or lefts["amount"]:
        contaminated = True

    row = BOQRow(
        kind="item", page=page, sr_no=sr_no, item_no=values["item_no"],
        description=values["description"], unit=unit,
        quantity=nums["quantity"], quantity_raw=values["quantity"],
        rate=nums["rate"], original_rate=nums["rate"], amount=nums["amount"],
        section=section, flags=flags,
    )
    return row, contaminated


def _check_item(row: BOQRow, cfg) -> None:
    """Add flags for problems inside a single item row."""
    if row.unit and row.quantity is None:
        row.flags.append(_flag("quantity_unreadable",
                               f"Quantity could not be read (found '{row.quantity_raw}')."))
    if row.quantity is not None and not row.unit:
        row.flags.append(_flag("unit_missing", "Quantity is given but the unit is empty."))
    if not row.description:
        row.flags.append(_flag("description_empty", "Description is empty."))
    if row.quantity is not None and row.rate is not None and row.amount is not None:
        expected = row.quantity * row.rate
        diff = abs(expected - row.amount)
        if diff > cfg["amount_tolerance_abs"] and diff > cfg["amount_tolerance_rel"] * abs(row.amount):
            row.flags.append(_flag(
                "amount_mismatch",
                f"Quantity x rate = {expected:,.2f} but the printed amount is {row.amount:,.2f}."))


def _classify(values, row: BOQRow, first_in_table: bool, prev_row):
    """Decide what kind of row this is. Returns the kind (and may change the row)."""
    has_numbers = any(v is not None for v in (row.quantity, row.rate, row.amount))
    has_unit_or_qty = bool(row.unit) or row.quantity is not None
    text_all = " ".join(v for v in values.values() if v).lower()

    if not has_unit_or_qty and re.search(r"\btotal\b", text_all):
        return "total"
    if not has_unit_or_qty and not has_numbers:
        if (row.sr_no is None and not row.item_no and row.description
                and first_in_table and prev_row is not None):
            return "continuation"
        if row.item_no.lower().startswith("note") or row.description.lower().startswith("note"):
            return "note"
        if row.item_no or row.description:
            return "section"
        return "unknown"
    return "item"


# --------------------------------------------------------------------------
# Main parsing
# --------------------------------------------------------------------------
def _page_job(text: str):
    for line in (text or "").splitlines():
        m = re.match(r"^\s*Job:\s*(.+?)\s*$", line)
        if m:
            return m.group(1)
    return None


def parse_boq_tables(pages: list) -> ParseResult:
    """pages: list of {"page": int, "text": str, "tables": [list of rows]}."""
    settings = load_settings()
    cfg = settings["boq_checks"]
    aliases = _alias_lookup()
    result = ParseResult()
    table = None          # the BOQTable being filled
    mapping = header_len = None
    current_job = None
    section = ""

    for pg in pages:
        page_no = pg["page"]
        job_line = _page_job(pg.get("text", ""))
        if job_line:
            current_job = job_line

        for raw in pg.get("tables", []):
            if not raw:
                continue
            found = _find_header(raw, aliases)
            start = 0
            if found:
                h_idx, mapping = found
                header_len = len(raw[h_idx])
                title_rows = [_clean(c) for r in raw[:h_idx] for c in r[:1] if _clean(c)]
                if title_rows:
                    job = title_rows[0]
                    current_job = job
                else:
                    job = current_job or f"BOQ {len(result.tables) + 1}"
                    current_job = job
                if table is None or table.job != job:
                    table = BOQTable(job=job, columns=[mapping[c] for c in sorted(mapping)])
                    result.tables.append(table)
                    section = ""
                start = h_idx + 1
            elif table is not None and mapping and len(raw[0]) == header_len:
                table.warnings.append(f"Page {page_no}: table has no header row; "
                                      "used the column layout of the previous page.")
            else:
                continue   # not a BOQ table

            if page_no not in table.pages:
                table.pages.append(page_no)

            first = True
            for r in raw[start:]:
                if not any(_clean(c) for c in r):
                    continue
                values, aligned = _align(r, header_len, mapping)
                if _find_header([r], aliases):       # repeated header row
                    continue
                row, noisy = _make_row(values, aligned, page_no, section)
                prev = table.rows[-1] if table.rows else None
                kind = _classify(values, row, first, prev)
                first = False

                if kind == "continuation":
                    if prev is not None and prev.kind == "item":
                        prev.description = f"{prev.description} {row.description}".strip()
                        prev.flags.append(_flag(
                            "joined_across_pages",
                            f"Description continued from page {page_no}; joined to this row."))
                        continue
                    kind = "unknown"
                row.kind = kind

                if kind == "total":
                    value = None
                    for f in ("amount", "rate", "quantity"):
                        v, _ = parse_number(values[f])
                        if v is not None:
                            value = v
                            break
                    label = values["description"] or values["item_no"] or values["sr_no"] or "Total"
                    grand = "grand" in " ".join(values.values()).lower()
                    if grand:
                        label = "GRAND TOTAL"
                    row.description, row.amount = label, value
                    table.totals.append({"label": label, "value": value,
                                         "grand": grand, "page": page_no})
                elif kind == "item":
                    if noisy or not aligned:
                        row.item_no = _strip_footer_words(row.item_no)
                        row.flags.append(_flag(
                            "footer_noise",
                            "Page footer text was mixed into this row and was removed. "
                            "Check the values against the PDF." if aligned else
                            "This row has a different number of columns than the table "
                            "header. Check the values against the PDF."))
                    _check_item(row, cfg)
                elif kind == "section":
                    section = f"{row.item_no} {row.description}".strip()
                    row.description = section
                elif kind == "unknown":
                    row.flags.append(_flag("unclassified_row",
                                           "This row could not be classified. Check against the PDF."))
                table.rows.append(row)

    for t in result.tables:
        _check_sequence(t)
    return result


def _check_sequence(table: BOQTable) -> None:
    """Row numbers (Sr. No) should run 1, 2, 3 ... without gaps or repeats."""
    prev = None
    for row in table.rows:
        if row.sr_no is None:
            continue
        if prev is not None and row.sr_no != prev + 1:
            if row.sr_no == prev:
                msg = f"Sr. No {row.sr_no} appears twice (page {row.page})."
            else:
                msg = (f"Sr. No jumps from {prev} to {row.sr_no} (page {row.page}); "
                       "a row may be missing.")
            table.warnings.append(msg)
            row.flags.append(_flag("sr_no_sequence", msg))
        prev = row.sr_no


def parse_boq(pdf_path) -> ParseResult:
    """Read a tender PDF and return every BOQ table found in it."""
    pages, no_text = [], []
    with pdfplumber.open(Path(pdf_path)) as doc:
        for i, page in enumerate(doc.pages, start=1):
            text = page.extract_text() or ""
            if len(text.strip()) < 50:
                no_text.append(i)
            tables = page.extract_tables() if text.strip() else []
            pages.append({"page": i, "text": text, "tables": tables})
            page.close()
    result = parse_boq_tables(pages)
    result.page_texts = [pg["text"] for pg in pages]
    if no_text:
        result.warnings.append(
            f"{len(no_text)} page(s) have no text layer (pages {no_text[:10]}"
            f"{'...' if len(no_text) > 10 else ''}); they look scanned and need OCR.")
    if not result.tables:
        result.warnings.append("No BOQ table was found in this PDF.")
    return result
