"""Row selection and rate editing for one BOQ table. Plain code, no LLM.

Flow:  command -> plan (a preview, nothing changes) -> apply -> undo if needed
"""
import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

OPS = ("percent", "add", "set")
FIELDS = ("rate", "quantity", "unit", "description", "item_no")
NUMERIC_FIELDS = ("rate", "quantity")


class StalePlanError(Exception):
    """The table changed after the preview was made."""


def _dec(x):
    return Decimal(str(x))


def money(x) -> float:
    """Round to 2 decimals, halves rounded up (0.055 -> 0.06)."""
    return float(_dec(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------- selecting rows
def expand_numbers(text: str) -> list:
    """'3, 5, 10-12' -> [3, 5, 10, 11, 12];  '3 to 5 and 9' -> [3, 4, 5, 9]."""
    if not text or not text.strip():
        return []
    t = text.lower().replace("\u2013", "-").replace("\u2014", "-")
    t = re.sub(r"\b(items?|rows?|sr\.?\s*nos?\.?|serial)\b", " ", t)
    t = re.sub(r"\b(to|through|until)\b", "-", t)
    out = []
    for part in re.split(r"[,;&]|\band\b", t):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a > b:
                raise ValueError(f"The range '{part}' goes backwards.")
            out.extend(range(a, b + 1))
        elif re.fullmatch(r"\d+", part):
            out.append(int(part))
        else:
            raise ValueError(f"Could not read '{part}' as row numbers.")
    seen = set()
    return [n for n in out if not (n in seen or seen.add(n))]


def _norm_ref(text) -> str:
    """'7-198.' and '7-198' are the same reference."""
    return re.sub(r"[\s.]+$", "", " ".join((text or "").lower().split()))


def _has_word(text, keyword) -> bool:
    """Keyword found at the start of a word: 'door' matches 'doors', not 'indoor'."""
    k = (keyword or "").lower().strip()
    return bool(k) and re.search(r"(?<![a-z0-9])" + re.escape(k), (text or "").lower()) is not None


def _split_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        return [x.strip() for x in re.split(r"[;,]", value) if x.strip()]
    return [str(x).strip() for x in value if str(x).strip()]


@dataclass
class Selector:
    """Names the rows to change. A row is chosen if it matches ANY of the three parts."""
    sr_nos: list = field(default_factory=list)       # Sr. No. values
    item_nos: list = field(default_factory=list)     # Ref No. / Item No. values
    keywords: list = field(default_factory=list)     # words in the description
    keywords_all: bool = False                       # True: description needs every keyword

    @classmethod
    def from_spec(cls, numbers="", item_nos=None, keywords=None, keywords_all=False):
        return cls(sr_nos=expand_numbers(numbers), item_nos=_split_list(item_nos),
                   keywords=_split_list(keywords), keywords_all=keywords_all)

    def is_empty(self) -> bool:
        return not (self.sr_nos or self.item_nos or self.keywords)

    def matches(self, row) -> bool:
        if row.sr_no is not None and row.sr_no in self.sr_nos:
            return True
        if self.item_nos and _norm_ref(row.item_no) in {_norm_ref(x) for x in self.item_nos}:
            return True
        if self.keywords:
            hits = [_has_word(row.description, k) for k in self.keywords]
            if all(hits) if self.keywords_all else any(hits):
                return True
        return False


# ---------------------------------------------------------------- the command
@dataclass
class EditCommand:
    op: str                 # "percent" | "add" | "set"
    value: object           # number, or text for unit / description / item_no
    selector: Selector
    field: str = "rate"

    def validate(self) -> None:
        if self.op not in OPS:
            raise ValueError(f"Unknown edit '{self.op}'. Use one of {OPS}.")
        if self.field not in FIELDS:
            raise ValueError(f"Unknown column '{self.field}'. Use one of {FIELDS}.")
        if self.selector.is_empty():
            raise ValueError("Name the rows to change (Sr. No, Ref No or a word from the description).")
        numeric_value = isinstance(self.value, (int, float)) and not isinstance(self.value, bool)
        if self.op in ("percent", "add"):
            if self.field != "rate":
                raise ValueError("Percent and add edits only work on the rate.")
            if not numeric_value:
                raise ValueError("The value must be a number.")
        elif self.field in NUMERIC_FIELDS:
            if not numeric_value or self.value < 0:
                raise ValueError(f"The {self.field} must be a number that is not negative.")
        elif not str(self.value).strip():
            raise ValueError(f"The new {self.field} cannot be empty.")

    def label(self) -> str:
        if self.op == "percent":
            word = "increase" if self.value >= 0 else "decrease"
            return f"{word} rate by {abs(self.value):g}%"
        if self.op == "add":
            return f"add {self.value:g} to the rate"
        return f"set {self.field} to {self.value}"


# ---------------------------------------------------------------- the preview
@dataclass
class Change:
    row_index: int
    sr_no: object
    item_no: str
    description: str
    page: int
    field: str
    old: object
    new: object = None
    old_amount: object = None
    new_amount: object = None
    skip_reason: str = ""


@dataclass
class EditPlan:
    command: EditCommand
    changes: list = field(default_factory=list)     # rows that will change
    skipped: list = field(default_factory=list)     # named rows that cannot change, with a reason
    not_found: list = field(default_factory=list)   # things you named that do not exist

    def amount_impact(self) -> float:
        total = 0.0
        for c in self.changes:
            if c.new_amount is not None:
                total += c.new_amount - (c.old_amount or 0.0)
        return round(total, 2)

    def to_rows(self) -> list:
        """The preview as a list of dicts (for a table in the app)."""
        return [{"Sr. No": c.sr_no, "Item No": c.item_no, "Description": c.description,
                 "Old": c.old, "New": c.new, "PDF page": c.page} for c in self.changes]


def _new_value(row, cmd):
    """Return (new value, skip reason) for one row."""
    f = cmd.field
    old = getattr(row, f)
    if cmd.op in ("percent", "add"):
        if row.rate is None:
            return None, "rate is blank"
        if cmd.op == "percent":
            new = money(_dec(row.rate) * (Decimal(1) + _dec(cmd.value) / Decimal(100)))
        else:
            new = money(_dec(row.rate) + _dec(cmd.value))
        if new < 0:
            return None, "result would be negative"
    elif f == "rate":
        new = money(cmd.value)
    elif f == "quantity":
        new = float(cmd.value)
    else:
        new = str(cmd.value).strip()
    if new == old:
        return None, "no change (already has this value)"
    return new, ""


def plan_edit(table, command) -> EditPlan:
    """Work out what an edit would do. Nothing in the table is changed."""
    command.validate()
    sel = command.selector
    plan = EditPlan(command=command)
    items = [(i, r) for i, r in enumerate(table.rows) if r.kind == "item"]

    present_sr = {r.sr_no for _, r in items}
    for n in sel.sr_nos:
        if n not in present_sr:
            plan.not_found.append(f"Sr. No {n} is not an item in this table")
    present_ref = {_norm_ref(r.item_no) for _, r in items}
    for x in sel.item_nos:
        if _norm_ref(x) not in present_ref:
            plan.not_found.append(f"No item has Ref/Item No '{x}'")
    for k in sel.keywords:
        if not any(_has_word(r.description, k) for _, r in items):
            plan.not_found.append(f"No item description contains '{k}'")

    for i, r in items:
        if not sel.matches(r):
            continue
        ch = Change(i, r.sr_no, r.item_no, r.description, r.page, command.field,
                    old=getattr(r, command.field))
        new, reason = _new_value(r, command)
        if reason:
            ch.skip_reason = reason
            plan.skipped.append(ch)
            continue
        ch.new = new
        if command.field in NUMERIC_FIELDS:
            qty = new if command.field == "quantity" else r.quantity
            rate = new if command.field == "rate" else r.rate
            ch.old_amount = r.effective_amount()
            ch.new_amount = money(_dec(qty) * _dec(rate)) if qty is not None and rate is not None else None
        plan.changes.append(ch)
    return plan


def _fmt(v) -> str:
    if v is None:
        return "(blank)"
    if isinstance(v, (int, float)):
        return f"{v:,.2f}"
    return str(v)[:30]


def format_plan(plan) -> str:
    """The preview as text."""
    cmd = plan.command
    lines = ["PREVIEW - nothing has been changed yet",
             f"Edit: {cmd.label()}  |  rows that will change: {len(plan.changes)}", ""]
    if plan.changes:
        lines.append(f"{'Sr.':>4}  {'Item no':<14} {'Description':<38} {'Old':>14} {'New':>14}  Page")
        for c in plan.changes:
            lines.append(f"{str(c.sr_no):>4}  {c.item_no[:14]:<14} {c.description[:38]:<38} "
                         f"{_fmt(c.old):>14} {_fmt(c.new):>14}  {c.page}")
        if cmd.field in NUMERIC_FIELDS:
            lines += ["", f"Effect on the BOQ total: {plan.amount_impact():+,.2f}"]
    if plan.skipped:
        lines += ["", "Named but NOT changed:"]
        lines += [f"  - Sr. No {c.sr_no}: {c.skip_reason}" for c in plan.skipped]
    if plan.not_found:
        lines += ["", "Not found:"] + [f"  - {m}" for m in plan.not_found]
    return "\n".join(lines)


# ---------------------------------------------------------------- applying and undo
_SNAPSHOT_FIELDS = ("rate", "amount", "quantity", "unit", "description", "item_no")


class EditSession:
    """Holds one BOQ table, applies confirmed edits and can undo them."""

    def __init__(self, table):
        self.table = table
        self.history = []
        for row in table.rows:          # remember the tender's rate before any edit
            if row.kind == "item" and not hasattr(row, "original_rate"):
                row.original_rate = row.rate

    def plan(self, command) -> EditPlan:
        return plan_edit(self.table, command)

    def apply(self, plan) -> int:
        """Apply a plan that you have looked at. Returns the number of rows changed."""
        if not plan.changes:
            return 0
        for c in plan.changes:                       # refuse if the table moved on
            row = self.table.rows[c.row_index]
            if row.kind != "item" or row.sr_no != c.sr_no or getattr(row, c.field) != c.old:
                raise StalePlanError("The table changed after this preview. Make the preview again.")
        snapshots = []
        for c in plan.changes:
            row = self.table.rows[c.row_index]
            snapshots.append((c.row_index, {f: getattr(row, f) for f in _SNAPSHOT_FIELDS}))
            setattr(row, c.field, c.new)
            if c.field in NUMERIC_FIELDS:
                row.amount = c.new_amount            # keep the amount in step with rate x quantity
        self.history.append({"label": plan.command.label(), "rows": len(plan.changes),
                             "snapshots": snapshots})
        return len(plan.changes)

    def undo(self) -> str:
        if not self.history:
            raise ValueError("Nothing to undo.")
        entry = self.history.pop()
        for idx, snap in entry["snapshots"]:
            for f, v in snap.items():
                setattr(self.table.rows[idx], f, v)
        return entry["label"]
