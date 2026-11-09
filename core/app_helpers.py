"""Helpers for the Streamlit screen (kept apart from app.py so they can be tested)."""
import pandas as pd

from core.boq_edit import EditCommand

OPERATIONS = ["Increase rate by %", "Decrease rate by %", "Add amount to the rate",
              "Set rate", "Set quantity", "Set unit"]

ITEM_COLUMNS = ["Sr. No", "Item No", "Section", "Description", "Unit", "Quantity",
                "Original Rate", "Rate", "Amount", "PDF page", "Review"]
REVIEW_COLUMNS = ["PDF page", "Sr. No", "Item No", "Problem", "Description"]


def build_command(operation, value_text, selector):
    """Turn the form choices into an EditCommand. Raises ValueError with a readable message."""
    text = (value_text or "").strip()
    if operation == "Set unit":
        return EditCommand("set", text, selector, field="unit")
    try:
        number = float(text.replace(",", ""))
    except ValueError:
        raise ValueError("Enter the value as a number, for example 10 or 2500.50.")
    if operation == "Increase rate by %":
        return EditCommand("percent", abs(number), selector)
    if operation == "Decrease rate by %":
        return EditCommand("percent", -abs(number), selector)
    if operation == "Add amount to the rate":
        return EditCommand("add", number, selector)
    if operation == "Set rate":
        return EditCommand("set", number, selector)
    if operation == "Set quantity":
        return EditCommand("set", number, selector, field="quantity")
    raise ValueError(f"Unknown edit: {operation}")


def fmt(value):
    return "n/a" if value is None else f"{value:,.2f}"


def show_value(value):
    if value is None or value == "":
        return "(blank)"
    if isinstance(value, (int, float)):
        return f"{value:,.2f}"
    return str(value)


def items_frame(table):
    rows = []
    for r in table.rows:
        if r.kind != "item":
            continue
        rows.append({
            "Sr. No": r.sr_no, "Item No": r.item_no, "Section": r.section,
            "Description": r.description, "Unit": r.unit, "Quantity": r.quantity,
            "Original Rate": getattr(r, "original_rate", r.rate), "Rate": r.rate,
            "Amount": r.effective_amount(), "PDF page": r.page,
            "Review": "\u26a0" if r.needs_review else ""})
    return pd.DataFrame(rows, columns=ITEM_COLUMNS)


def review_frame(table):
    rows = []
    for r in table.review_rows:
        for f in r.flags:
            rows.append({"PDF page": r.page, "Sr. No": r.sr_no, "Item No": r.item_no,
                         "Problem": f["message"], "Description": r.description[:90]})
    return pd.DataFrame(rows, columns=REVIEW_COLUMNS)
