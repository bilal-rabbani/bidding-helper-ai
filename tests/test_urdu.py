"""Phase 8 tests: glossary, checks, translation in batches, Excel sheet, chat."""
from pathlib import Path

import core.chat as chat_module
from core.boq_edit import EditSession
from core.boq_parser import parse_boq
from core.chat import handle_message
from core.excel_export import build_boq_workbook
from core.llm_router import AllKeysFailed, LLMResult
from core.urdu import (_problems, glossary_for, has_urdu, parse_glossary, set_urdu, translate_rows,
                       urdu_check_for, urdu_for)

FIX = Path(__file__).parent / "fixtures"
URDU2 = '{"translations":[{"n":1,"urdu":"اردو ایک"},{"n":2,"urdu":"اردو دو"}]}'
URDU1 = '{"translations":[{"n":1,"urdu":"اردو تین"}]}'


class FakeRouter:
    def __init__(self, *texts):
        self.texts, self.prompts = list(texts), []

    def complete(self, prompt, system="", **kw):
        self.prompts.append((system, prompt))
        text = self.texts.pop(0) if len(self.texts) > 1 else self.texts[0]
        return LLMResult(text, "gemini", "m", "Gemini key 1", ["a note"])


class DownRouter:
    def complete(self, *a, **k):
        raise AllKeysFailed("All keys are rate limited. Try again in about 60 seconds.")


def table_a():
    t = parse_boq(FIX / "tender_a_nust_boq.pdf").tables[0]
    return t, EditSession(t)


def test_glossary_parse_and_select():
    g = parse_glossary("# comment\ndoor = دروازہ\nFalse Ceiling = فالس سیلنگ\n\nnot a pair")
    assert g == {"door": "دروازہ", "false ceiling": "فالس سیلنگ"}
    terms = glossary_for(["Supply aluminium doors and indoor lights", "False ceiling work"], g)
    assert "false ceiling" in terms and "door" not in terms          # whole words only


def test_checks():
    en = "Supply 12 mm thick cement board, 1,200 x 600"
    assert _problems(en, "12 ملی میٹر موٹائی کا سیمنٹ بورڈ 1200 x 600", {"cement": "سیمنٹ"}) == ""
    assert _problems("size 12 mm", "سائز ١٢ ملی میٹر", {}) == ""                 # Urdu digits are accepted
    assert "numbers not kept" in _problems("size 12 mm", "سائز ملی میٹر", {})
    assert "glossary word not used" in _problems("a door", "ایک کھڑکی", {"door": "دروازہ"})
    assert "mostly English" in _problems("a door", "one door only", {})
    assert has_urdu("اردو") and not has_urdu("English")


def test_batches_attributes_and_stale_translations():
    t, _ = table_a()
    rows = t.items[:3]
    r = FakeRouter(URDU2, URDU1)
    stats, notes = translate_rows(rows, r, batch_size=2)
    assert stats["asked"] == 3 and stats["done"] == 3 and stats["failed"] == 0 and len(r.prompts) == 2
    assert [urdu_for(x) for x in rows] == ["اردو ایک", "اردو دو", "اردو تین"] and "a note" in notes
    again = translate_rows(rows, FakeRouter("never used"), batch_size=2)[0]
    assert again["asked"] == 0                                         # already translated: no new request
    rows[0].description += " (changed)"
    assert urdu_for(rows[0]) == ""                                     # old Urdu is ignored


def test_bad_answers_and_outages_do_not_crash():
    t, _ = table_a()
    rows = t.items[:2]
    assert translate_rows(rows, FakeRouter("hello there"))[0]["failed"] == 2
    english = '{"translations":[{"n":1,"urdu":"still english"},{"n":2,"urdu":"اردو"}]}'
    stats, _ = translate_rows(rows, FakeRouter(english))
    assert stats["done"] == 1 and stats["failed"] == 1
    stats, notes = translate_rows(t.items[4:8], DownRouter(), batch_size=2)     # four fresh rows
    assert stats["failed"] == 4 and stats["done"] == 0 and notes


def test_correcting_a_translation():
    t, _ = table_a()
    row = t.items[0]
    set_urdu(row, "نیا متن", "edited by you")
    assert urdu_for(row) == "نیا متن" and urdu_check_for(row) == "edited by you"


def test_excel_gets_an_urdu_sheet_only_when_there_is_urdu():
    result = parse_boq(FIX / "tender_b_jiap_boq.pdf")
    assert build_boq_workbook(result, "x.pdf").sheetnames == ["BOQ", "Summary"]
    row = result.tables[0].items[0]
    set_urdu(row, "فرش کی تنصیب", "numbers not kept: 4")
    wb = build_boq_workbook(result, "x.pdf")
    assert wb.sheetnames == ["BOQ", "BOQ Urdu", "Summary"]
    ws = wb["BOQ Urdu"]
    assert ws.cell(5, 3).value == row.description and ws.cell(5, 4).value == "فرش کی تنصیب"
    assert ws.cell(5, 4).alignment.readingOrder == 2 and ws.cell(5, 4).alignment.horizontal == "right"
    assert ws.cell(5, 7).value == "numbers not kept: 4"


def test_chat_translates_named_rows():
    t, s = table_a()
    r = FakeRouter('{"intent":"translate","sr_nos":"3-4"}', URDU2)
    reply = handle_message("translate items 3 to 4 into urdu", t, s, r, [])
    assert reply.intent == "translate" and "Translated **2**" in reply.text and len(reply.rows) == 2
    assert [urdu_for(x) for x in t.items[:2]] == ["اردو ایک", "اردو دو"]


def test_chat_asks_which_rows_and_reads_all(monkeypatch):
    t, s = table_a()
    ask = handle_message("translate this into urdu", t, s, FakeRouter('{"intent":"translate"}'), [])
    assert ask.kind == "clarify" and "Which items" in ask.text
    monkeypatch.setattr(chat_module, "DRY_RUN", True)
    allrows = handle_message("translate the descriptions into urdu", t, s,
                             FakeRouter('{"intent":"translate"}'), [])
    assert allrows.intent == "translate" and "I would translate 42" in allrows.text
