"""Phase 3 tests: row selection, rate editing, preview and undo."""
from pathlib import Path

import pytest

from core.boq_edit import (EditCommand, EditSession, Selector, StalePlanError,
                           expand_numbers, format_plan, money, plan_edit)
from core.boq_parser import parse_boq

FIX = Path(__file__).parent / "fixtures"


def table_a():
    return parse_boq(FIX / "tender_a_nust_boq.pdf").tables[0]


def table_b():
    return parse_boq(FIX / "tender_b_jiap_boq.pdf").tables[0]


def snapshot(table):
    return [r.to_dict() for r in table.rows]


def test_expand_numbers():
    assert expand_numbers("3, 5, 10-12") == [3, 5, 10, 11, 12]
    assert expand_numbers("items 3 to 5 and 9") == [3, 4, 5, 9]
    assert expand_numbers("") == []
    assert expand_numbers("4, 4, 5") == [4, 5]
    with pytest.raises(ValueError):
        expand_numbers("5-3")
    with pytest.raises(ValueError):
        expand_numbers("door")


def test_money_rounds_half_up_to_two_decimals():
    assert money(0.055) == 0.06
    assert money(1523 * 1.1) == 1675.30


def test_preview_changes_nothing():
    t = table_a()
    before = snapshot(t)
    plan = EditSession(t).plan(EditCommand("percent", 10, Selector.from_spec(numbers="3, 5")))
    assert [c.sr_no for c in plan.changes] == [3, 5]
    assert snapshot(t) == before
    assert "nothing has been changed" in format_plan(plan)


def test_percent_change_only_named_rows_and_original_rate_kept():
    t = table_a()
    before = {r.sr_no: r.rate for r in t.items}
    s = EditSession(t)
    plan = s.plan(EditCommand("percent", 10, Selector.from_spec(numbers="3, 5")))
    assert s.apply(plan) == 2
    for r in t.items:
        if r.sr_no in (3, 5):
            assert r.rate == money(before[r.sr_no] * 1.1)
            assert r.original_rate == before[r.sr_no]
            assert r.amount == money(r.quantity * r.rate)
        else:
            assert r.rate == before[r.sr_no]
            assert r.original_rate == before[r.sr_no]


def test_undo_restores_everything():
    t = table_a()
    before = snapshot(t)
    s = EditSession(t)
    s.apply(s.plan(EditCommand("percent", 25, Selector.from_spec(keywords="door"))))
    assert snapshot(t) != before
    s.undo()
    assert snapshot(t) == before
    with pytest.raises(ValueError):
        s.undo()


def test_selection_by_ref_number_keyword_and_union():
    t = table_a()
    by_ref = plan_edit(t, EditCommand("percent", 5, Selector.from_spec(item_nos="7-198")))
    assert [c.sr_no for c in by_ref.changes] == [3]                  # '7-198.' matches '7-198'
    kw = plan_edit(t, EditCommand("percent", 5, Selector.from_spec(keywords="door")))
    assert kw.changes and all("door" in c.description.lower() for c in kw.changes)
    union = plan_edit(t, EditCommand("percent", 5, Selector.from_spec(numbers="3", item_nos="7-198")))
    assert [c.sr_no for c in union.changes] == [3]                   # same row named twice, once


def test_nothing_named_is_refused():
    with pytest.raises(ValueError):
        plan_edit(table_a(), EditCommand("percent", 10, Selector()))


def test_unknown_rows_are_reported():
    plan = plan_edit(table_a(), EditCommand("percent", 10, Selector.from_spec(numbers="3, 999")))
    assert [c.sr_no for c in plan.changes] == [3]
    assert any("999" in m for m in plan.not_found)


def test_blank_rates_are_skipped_not_guessed():
    t = table_b()
    s = EditSession(t)
    plan = s.plan(EditCommand("percent", 10, Selector.from_spec(numbers="1-5")))
    assert plan.changes == [] and len(plan.skipped) == 5
    assert all(c.skip_reason == "rate is blank" for c in plan.skipped)
    assert s.apply(plan) == 0


def test_set_rate_on_blank_row_fills_amount():
    t = table_b()
    s = EditSession(t)
    s.apply(s.plan(EditCommand("set", 1000, Selector.from_spec(numbers="1"))))
    row = t.items[0]
    assert row.rate == 1000 and row.amount == money(row.quantity * 1000)
    assert row.original_rate is None


def test_negative_result_is_skipped():
    plan = plan_edit(table_a(), EditCommand("percent", -150, Selector.from_spec(numbers="3")))
    assert plan.changes == [] and plan.skipped[0].skip_reason == "result would be negative"


def test_set_text_and_quantity_fields():
    t = table_a()
    s = EditSession(t)
    s.apply(s.plan(EditCommand("set", "Sqm", Selector.from_spec(numbers="3"), field="unit")))
    s.apply(s.plan(EditCommand("set", 60, Selector.from_spec(numbers="3"), field="quantity")))
    row = next(r for r in t.items if r.sr_no == 3)
    assert row.unit == "Sqm" and row.quantity == 60
    assert row.amount == money(60 * row.rate)


def test_old_preview_cannot_be_applied_twice():
    t = table_a()
    s = EditSession(t)
    plan = s.plan(EditCommand("percent", 10, Selector.from_spec(numbers="3")))
    s.apply(plan)
    with pytest.raises(StalePlanError):
        s.apply(plan)


def test_total_moves_with_the_rates():
    t = table_a()
    before = t.sum_amount()
    s = EditSession(t)
    plan = s.plan(EditCommand("percent", 10, Selector.from_spec(numbers="1-46")))
    s.apply(plan)
    assert abs(t.sum_amount() - before * 1.1) < 50
    assert abs(plan.amount_impact() - (t.sum_amount() - before)) < 5


def test_bad_commands_are_refused():
    sel = Selector.from_spec(numbers="3")
    for cmd in (EditCommand("multiply", 2, sel), EditCommand("percent", "ten", sel),
                EditCommand("percent", 10, sel, field="unit"), EditCommand("set", -5, sel),
                EditCommand("set", "  ", sel, field="unit")):
        with pytest.raises(ValueError):
            plan_edit(table_a(), cmd)
