"""Chat tests with a fake AI: parsing, checks against the person's words, sections, flows."""
from pathlib import Path

import pytest

from core.boq_edit import EditCommand, EditSession, Selector, plan_edit
from core.boq_parser import parse_boq
from core.chat import (HELP_TEXT, _selector, build_prompt, command_from_dict, extract_json,
                       handle_message, reconcile, table_context)
from core.llm_router import AllKeysFailed, LLMResult

FIX = Path(__file__).parent / "fixtures"
EDIT_3_5 = '{"intent":"edit","op":"percent","field":"rate","value":10,"sr_nos":"3, 5"}'


class FakeRouter:
    def __init__(self, *texts):
        self.texts, self.prompts = list(texts), []

    def complete(self, prompt, system="", **kw):
        self.prompts.append((system, prompt))
        text = self.texts.pop(0) if len(self.texts) > 1 else self.texts[0]
        return LLMResult(text, "gemini", "m", "Gemini key 1", [])


class DownRouter:
    def complete(self, *a, **k):
        raise AllKeysFailed("All keys are rate limited. Try again in about 60 seconds.")


def table_a():
    t = parse_boq(FIX / "tender_a_nust_boq.pdf").tables[0]
    return t, EditSession(t)


def snapshot(t):
    return [r.to_dict() for r in t.rows]


def srs(t, sel):
    return {r.sr_no for r in t.items if sel.matches(r)}


def test_extract_json():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('Sure!\n```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json("no json here") is None
    assert extract_json("{broken") is None


def test_command_from_dict():
    c = command_from_dict({"op": "percent", "value": "-5%", "sr_nos": [3, 4]})
    assert (c.op, c.value, c.field, c.selector.sr_nos) == ("percent", -5.0, "rate", [3, 4])
    c = command_from_dict({"op": "set", "field": "rate", "value": "Rs. 2,500.50", "sr_nos": "9"})
    assert c.value == 2500.5
    c = command_from_dict({"op": "set", "field": "unit", "value": "Sqm", "sr_nos": "14"})
    assert (c.field, c.value) == ("unit", "Sqm")
    c = command_from_dict({"op": "add", "value": -50, "keywords": ["door"]})
    assert c.selector.keywords == ["door"]
    for bad in ({"op": "multiply", "value": 2, "sr_nos": "3"},
                {"op": "percent", "value": "ten", "sr_nos": "3"},
                {"op": "percent", "value": 10},
                {"op": "set", "field": "colour", "value": "x", "sr_nos": "3"}):
        with pytest.raises(ValueError):
            command_from_dict(bad)


def test_table_context_and_prompt():
    t, _ = table_a()
    ctx = table_context(t)
    assert "A. CIVIL Works: 3-24" in ctx and "C. HVAC Works: 42-46" in ctx and "3 to 46" in ctx
    prompt = build_prompt("hello", t, [{"role": "user", "content": "earlier"}])
    assert "BOQ INFO" in prompt and "User: earlier" in prompt and "NEW MESSAGE:\nhello" in prompt


def test_edit_makes_a_preview_and_changes_nothing():
    t, s = table_a()
    before = snapshot(t)
    reply = handle_message("increase items 3 and 5 by 10%", t, s, FakeRouter(EDIT_3_5), [])
    assert reply.kind == "edit" and [c.sr_no for c in reply.plan.changes] == [3, 5]
    assert len(reply.rows) == 2 and "Apply" in reply.text
    assert snapshot(t) == before
    assert s.apply(reply.plan) == 2


def test_undo_works_without_the_ai():
    t, s = table_a()
    before = snapshot(t)
    reply = handle_message("edit", t, s, FakeRouter(EDIT_3_5), [])
    s.apply(reply.plan)
    r = FakeRouter("{}")
    assert handle_message("undo that", t, s, r, []).kind == "undo"
    assert snapshot(t) == before and r.prompts == []
    assert "nothing to undo" in handle_message("undo", t, s, None, []).text.lower()


def test_json_inside_code_fences_is_accepted():
    t, s = table_a()
    reply = handle_message("x", t, s, FakeRouter("Here you go:\n```json\n" + EDIT_3_5 + "\n```"), [])
    assert reply.kind == "edit"


def test_unclear_requests_are_not_executed():
    t, s = table_a()
    reply = handle_message("raise the rates", t, s,
                           FakeRouter('{"intent":"clarify","question":"Which rows?"}'), [])
    assert reply.kind == "clarify" and reply.text == "Which rows?" and reply.plan is None
    reply = handle_message("raise the rates", t, s,
                           FakeRouter('{"intent":"edit","op":"percent","value":10}'), [])
    assert reply.plan is None and reply.kind == "clarify"


def test_other_intents():
    t, s = table_a()
    assert "API keys" in handle_message("x", t, s, FakeRouter('{"intent":"tender_question"}')).text
    assert "phase 8" in handle_message("x", t, s, FakeRouter('{"intent":"translate"}')).text
    assert "cannot" in handle_message("x", t, s, FakeRouter('{"intent":"unsupported"}')).text
    rev = handle_message("x", t, s, FakeRouter('{"intent":"show_review"}'))
    assert rev.rows and rev.rows[0]["PDF page"] == 12
    assert "Items: 42" in handle_message("x", t, s, FakeRouter('{"intent":"show_summary"}')).text
    rows = handle_message("x", t, s, FakeRouter('{"intent":"show_rows","sr_nos":"3-4"}'))
    assert [r["Sr. No"] for r in rows.rows] == [3, 4]


def test_failures_are_reported_not_raised():
    t, s = table_a()
    assert handle_message("x", t, s, FakeRouter("I think you want a raise")).kind == "error"
    assert handle_message("x", t, s, FakeRouter('{"intent":"dance"}')).kind == "error"
    down = handle_message("x", t, s, DownRouter())
    assert down.kind == "error" and "rate limited" in down.text
    assert handle_message("x", t, s, None).kind == "error"
    assert handle_message("help", t, s, None).text == HELP_TEXT


def test_sections_by_name():
    t, _ = table_a()
    assert srs(t, Selector.from_spec(sections="electrical works")) == set(range(26, 41))
    assert srs(t, Selector.from_spec(sections="civil works")) == set(range(3, 25))
    assert srs(t, Selector.from_spec(sections="HVAC")) == set(range(42, 47))
    assert srs(t, Selector.from_spec(sections=["A. CIVIL Works"])) == set(range(3, 25))


def test_unknown_section_is_reported():
    t, _ = table_a()
    plan = plan_edit(t, EditCommand("percent", 5, Selector.from_spec(sections="plumbing")))
    assert plan.changes == [] and any("plumbing" in m for m in plan.not_found)


def test_plain_numbers_in_item_nos_are_sr_nos():
    t, _ = table_a()
    sel = _selector({"item_nos": ["7"]}, t)
    assert sel.sr_nos == [7] and sel.item_nos == []
    sel = _selector({"item_nos": ["7-198"], "sr_nos": "4"}, t)
    assert sel.sr_nos == [4] and sel.item_nos == ["7-198"]


def test_numbers_and_signs_follow_the_message():
    t, _ = table_a()
    d = {"intent": "edit", "op": "percent", "value": 12, "sr_nos": "3, 5, 10-12"}
    assert reconcile(d, "increase the rates of items 3, 5 and 10 to 12 by 10%", t) and d["value"] == 10
    d = {"intent": "edit", "op": "percent", "value": 100, "sr_nos": "3-5"}
    reconcile(d, "decrease the rate of items 3 to 5 by Rs 100", t)
    assert (d["op"], d["value"]) == ("add", -100)
    d = {"intent": "edit", "op": "percent", "value": 5, "sr_nos": "7"}
    reconcile(d, "reduce rate for item 7 by 5 percent", t)
    assert d["value"] == -5
    d = {"intent": "edit", "op": "percent", "value": -10, "sr_nos": "3-5"}
    reconcile(d, "increase items 3 to 5 by 10%", t)
    assert d["value"] == 10


def test_intent_fallbacks():
    t, _ = table_a()
    d = {"intent": "show_rows"}
    reconcile(d, "show me the items that need review", t)
    assert d["intent"] == "show_review"
    d = {"intent": "clarify"}
    reconcile(d, "how many items are there and what is the total?", t)
    assert d["intent"] == "show_summary"
    d = {"intent": "show_rows", "sr_nos": "3-4"}
    reconcile(d, "show items 3 to 4", t)
    assert d["intent"] == "show_rows"
    d = {"intent": "clarify", "question": "Which rows?"}
    reconcile(d, "increase the rates by 10%", t)
    assert d["intent"] == "clarify"


def test_whole_flow_with_the_old_mistakes():
    t, s = table_a()
    wrong = '{"intent":"edit","op":"percent","value":5,"item_nos":["7"]}'
    reply = handle_message("reduce rate for item 7 by 5 percent", t, s, FakeRouter(wrong), [])
    assert [c.sr_no for c in reply.plan.changes] == [7]
    assert reply.command.value == -5 and reply.model == "gemini/m"
    by_section = '{"intent":"edit","op":"percent","value":10,"sections":["electrical works"]}'
    reply = handle_message("increase the electrical works by 10%", t, s, FakeRouter(by_section), [])
    assert {c.sr_no for c in reply.plan.changes} == set(range(26, 41))
