"""Phase 4b tests: screen helpers and a start-up check of the app."""
from pathlib import Path

import pytest

from core.app_helpers import OPERATIONS, build_command, items_frame, review_frame
from core.boq_edit import Selector
from core.boq_parser import parse_boq

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures"


def table_a():
    return parse_boq(FIX / "tender_a_nust_boq.pdf").tables[0]


def test_build_command_variants():
    sel = Selector.from_spec(numbers="3")
    c = build_command("Increase rate by %", "10", sel)
    assert (c.op, c.value, c.field) == ("percent", 10.0, "rate")
    assert build_command("Decrease rate by %", "10", sel).value == -10.0
    c = build_command("Add amount to the rate", "-50", sel)
    assert (c.op, c.value) == ("add", -50.0)
    c = build_command("Set rate", "2,500.50", sel)
    assert (c.op, c.value, c.field) == ("set", 2500.5, "rate")
    assert build_command("Set quantity", "60", sel).field == "quantity"
    c = build_command("Set unit", "Sqm", sel)
    assert (c.value, c.field) == ("Sqm", "unit")
    with pytest.raises(ValueError):
        build_command("Set rate", "abc", sel)
    assert len(OPERATIONS) == 6


def test_items_frame():
    df = items_frame(table_a())
    assert len(df) == 42
    assert list(df.columns)[:3] == ["Sr. No", "Item No", "Section"]
    assert (df["Review"] == "\u26a0").sum() == 1


def test_review_frame():
    df = review_frame(table_a())
    assert len(df) == 1 and df.iloc[0]["PDF page"] == 12


def test_app_starts_without_errors():
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    assert not at.exception
