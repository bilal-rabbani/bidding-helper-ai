"""Save and load: everything survives, no keys are saved, bad files give clear messages."""
import json
from pathlib import Path

import pytest

from core.boq_edit import EditCommand, EditSession, Selector
from core.boq_parser import parse_boq
from core.chat import handle_message
from core.excel_export import build_boq_workbook
from core.session_file import FORMAT, SessionFileError, load_session, to_session_bytes
from core.tender_index import TenderIndex
from core.urdu import set_urdu, urdu_for

FIX = Path(__file__).parent / "fixtures"
CHAT = [{"role": "user", "content": "increase items 3 and 5 by 10%"},
        {"role": "assistant", "content": "I understood ...", "notes": ["a note"],
         "rows": [{"Sr. No": 3, "Old": "1,523.00", "New": "1,675.30"}]}]
FACTS = {"rows": [{"Group": "Dates and periods", "Fact": "Bid validity", "Value": "182 Days",
                   "Page": "p.37", "Check": "verified"}], "notes": [], "file": "a.pdf"}


def edited_result():
    result = parse_boq(FIX / "tender_a_nust_boq.pdf")
    table = result.tables[0]
    session = EditSession(table)
    session.apply(session.plan(EditCommand("percent", 10, Selector.from_spec(numbers="3, 5"))))
    set_urdu(table.items[0], "فرش کی تنصیب", "edited by you")
    table.urdu_glossary = "door = دروازہ"
    return result


def test_everything_survives_a_save_and_load():
    result = edited_result()
    data = load_session(to_session_bytes(result, "a.pdf", CHAT, FACTS))
    assert [t.to_dict() for t in data.result.tables] == [t.to_dict() for t in result.tables]
    assert data.chat == CHAT and data.key_facts == FACTS and data.file_name == "a.pdf"
    assert data.result.page_texts == result.page_texts and data.result.warnings == result.warnings
    original = {r.sr_no: r.rate for r in parse_boq(FIX / "tender_a_nust_boq.pdf").tables[0].items}
    row3 = next(r for r in data.result.tables[0].items if r.sr_no == 3)
    assert row3.original_rate == original[3] and row3.rate == pytest.approx(original[3] * 1.1, abs=0.01)
    assert urdu_for(data.result.tables[0].items[0]) == "فرش کی تنصیب"
    assert data.result.tables[0].urdu_glossary == "door = دروازہ"
    assert isinstance(data.tender, TenderIndex) and data.tender.n_pages == 25
    assert data.sessions[0].history == []                       # the undo history is not saved
    assert build_boq_workbook(data.result, "a.pdf").sheetnames == ["BOQ", "BOQ Urdu", "Summary"]


def test_two_tables_survive():
    result = parse_boq(FIX / "tender_c_pidcl_boq.pdf")
    data = load_session(to_session_bytes(result, "c.pdf"))
    assert len(data.result.tables) == 2
    assert [t.to_dict() for t in data.result.tables] == [t.to_dict() for t in result.tables]
    assert data.chat == [] and data.key_facts is None


def test_the_file_holds_no_keys_and_only_the_expected_parts():
    raw = to_session_bytes(edited_result(), "a.pdf", CHAT, FACTS)
    payload = json.loads(raw)
    assert set(payload) == {"format", "version", "saved_at", "file_name", "warnings", "page_texts",
                            "tables", "chat", "key_facts"}
    assert payload["format"] == FORMAT
    text = raw.decode("utf-8")
    assert "AIza" not in text and "gsk_" not in text
    assert "فرش" in text                                          # Urdu is saved as readable text


@pytest.mark.parametrize("raw,word", [
    (b"", "not a session"),
    (b"hello", "not a session"),
    (b"\xff\xfe\x00", "not a session"),
    (json.dumps({"format": "other"}).encode(), "not a Bidding Helper"),
    (json.dumps({"format": FORMAT, "version": 99, "tables": []}).encode(), "newer"),
    (json.dumps({"format": FORMAT, "version": "x", "tables": []}).encode(), "damaged"),
    (json.dumps({"format": FORMAT, "version": 1}).encode(), "damaged"),
    (json.dumps({"format": FORMAT, "version": 1, "tables": [{"job": "x", "rows": [{"page": 1}]}]}).encode(), "damaged"),
])
def test_bad_files_give_clear_messages(raw, word):
    with pytest.raises(SessionFileError) as e:
        load_session(raw)
    assert word in str(e.value)


def test_a_loaded_session_works_with_the_chat():
    data = load_session(to_session_bytes(edited_result(), "a.pdf"))
    table, session = data.result.tables[0], data.sessions[0]
    assert "nothing to undo" in handle_message("undo", table, session, None, []).text.lower()
