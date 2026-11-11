"""Phase 6 tests: printed pages, headings, passages, forms, search, answers, key facts."""
from pathlib import Path

from core.boq_edit import EditSession
from core.boq_parser import parse_boq
from core.chat import handle_message
from core.llm_router import AllKeysFailed, LLMResult
from core.tender_index import (TenderIndex, find_forms, heading_of, page_label, printed_pages)
from core.tender_qa import answer_question, extract_key_facts, looks_like_tender_question, quote_in

FIX = Path(__file__).parent / "fixtures"
FOOT = "e-Pak Acquisition and Disposal System (EPADS) generated document | \u00a9 2026 Page {n} of 9"


def pages():
    toc = "Table of Contents\n" + "\n".join(f"Section {r} Topic {i}" for i, r in
                                             enumerate(["I", "II", "III", "IV", "V", "VI", "VII"]))
    return [
        toc,
        "Section I - Invitation for Bids\nBids will be opened on December 2, 2026 02:00 PM by the Procuring Agency.\n" + FOOT.format(n=1),
        "Bid Data Sheet\n16.1 The Bids/Bid Validity period shall be: 182 Days\n17.1 Bid Security 2% of the bid amount "
        "in the form of Pay Order\n20. The Performance guarantee shall: 10.00%.\n" + FOOT.format(n=2),
        "Form 9: Bid Securing Declaration\nI declare that I will not withdraw my bid.\n" + FOOT.format(n=3),
        "Form EXP - 4.1\nExperience of the bidder in similar works.\n" + FOOT.format(n=4),
        "Form EXP - 4.1 (cont.)\nMore rows of the experience table.\n" + FOOT.format(n=5),
        "Tender fee Rs 3,000 in the form of Pay Order.\nCompletion period is 180 days.",
        "Eligibility Criteria\nValid registration with PEC in category C-6 or above.\n" + FOOT.format(n=7),
    ]


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


def test_printed_pages_and_labels():
    pr = printed_pages(pages())
    assert pr[1] == 1 and pr[2] == 2 and pr[6] == 6          # page 7 has no marker: inferred from its neighbours
    only_first = ["Page 1 of 9"] + ["x"] * 7
    assert printed_pages(only_first)[0] == 1 and printed_pages(only_first)[6] is None
    assert printed_pages(["no marks", "none"]) == [None, None]
    assert page_label(5, 5) == "p.5" and page_label(5, None) == "p.5"
    assert page_label(40, 37) == "PDF p.40 (printed p.37)"


def test_headings():
    assert heading_of("Section III Bid Data Sheet (BDS)")
    assert heading_of("Form 9: Bid Securing Declaration")
    assert heading_of("Eligibility Criteria")
    assert heading_of("The bidder shall submit the following documents together with the bid") is None


def test_passages_and_toc():
    t = TenderIndex(pages())
    assert any(p.section == "Table of contents" for p in t.passages)
    assert all(p.section != "Table of contents" for p in t.searchable)
    bds = [p for p in t.passages if p.pdf_page == 3]
    assert bds and bds[0].section == "Bid Data Sheet" and "182 Days" in bds[0].text
    assert all("e-Pak Acquisition" not in p.text for p in t.passages)
    assert all(len(p.text) < 1300 for p in t.passages)


def test_forms_found_once_and_toc_skipped():
    t = TenderIndex(pages())
    labels = [f["label"] for f in t.forms]
    assert labels == ["Form 9", "Form EXP - 4.1"]
    assert t.forms[0]["title"] == "Bid Securing Declaration" and t.forms[0]["pdf_page"] == 4


def test_search_finds_the_right_pages_and_knows_synonyms():
    t = TenderIndex(pages())
    assert 3 in [p.pdf_page for p in t.search("What is the bid security?")[:2]]
    assert 3 in [p.pdf_page for p in t.search("How long must bids remain valid?")[:2]]
    assert 3 in [p.pdf_page for p in t.search("What is the earnest money?")[:3]]
    assert 8 in [p.pdf_page for p in t.search("Which PEC category is required?")[:2]]
    assert t.search("zzzz qqqq") == []


def good(quote="Bid Validity period shall be: 182 Days"):
    return ('{"found": true, "answer": "Bids stay valid for 182 days.", "sources": ["P1", "P2"], '
            f'"quote": "{quote}"}}')


def test_answer_with_pages_and_verified_quote():
    t = TenderIndex(pages())
    a = answer_question("How long must bids remain valid?", t, FakeRouter(good()))
    assert a.found and a.verified and 3 in a.pages
    assert "182 days" in a.text and "**Source:**" in a.text and "PDF p.3 (printed p.2)" in a.text
    assert a.notes == ["a note"] and a.rows


def test_wrong_quote_is_flagged():
    t = TenderIndex(pages())
    a = answer_question("How long must bids remain valid?", t, FakeRouter(good("words that are not on the page")))
    assert a.found and not a.verified and "\u26a0" in a.text
    assert quote_in("Bid Validity period shall be 182 Days", t.search("validity")[:1])


def test_not_found_and_failures():
    t = TenderIndex(pages())
    a = answer_question("bid security amount", t, FakeRouter('{"found": false, "answer": "", "sources": [], "quote": ""}'))
    assert not a.found and "could not find" in a.text and "p." in a.text
    assert "could not read" in answer_question("bid security", t, FakeRouter("no json")).text
    assert "could not reach" in answer_question("bid security", t, DownRouter()).text
    assert "could not find anything" in answer_question("zzzz qqqq", t, FakeRouter(good())).text
    bad_ids = '{"found": true, "answer": "x", "sources": ["P99"], "quote": "x"}'
    a = answer_question("bid security", t, FakeRouter(bad_ids))
    assert a.found and a.pages == [] and "\u26a0" in a.text


def test_forms_question_includes_the_forms_list():
    t = TenderIndex(pages())
    r = FakeRouter(good())
    answer_question("What forms do I need to submit?", t, r)
    assert "FORMS FOUND IN THE DOCUMENT" in r.prompts[0][1] and "Form 9: Bid Securing Declaration" in r.prompts[0][1]
    r2 = FakeRouter(good())
    answer_question("How long must bids remain valid?", t, r2)
    assert "FORMS FOUND" not in r2.prompts[0][1]


def test_heuristic():
    for yes in ("what forms do I need to submit?", "when is the bid deadline?", "what is the bid security amount?"):
        assert looks_like_tender_question(yes)
    for no in ("increase items 3 to 5 by 10%", "how many items are there?", "show the door items", "undo"):
        assert not looks_like_tender_question(no)


def test_key_facts_checks():
    t = TenderIndex(pages())
    groups = [("Test", [("Validity", "bid validity period days remain valid"), ("Fee", "tender fee cost"),
                        ("Security", "bid security")])]
    reply = ('{"facts": [{"n": 1, "value": "182 Days", "source": "P1", "quote": "Bid Validity period shall be: 182 Days"},'
             '{"n": 2, "value": "", "source": "", "quote": ""},'
             '{"n": 3, "value": "99%", "source": "P1", "quote": "words that are not on the page"}]}')
    rows, notes = extract_key_facts(t, FakeRouter(reply), groups)
    assert [r["Check"] for r in rows] == ["verified", "not found", "check"]
    assert rows[0]["Value"] == "182 Days" and rows[0]["Page"].startswith("PDF p.3")
    rows, notes = extract_key_facts(t, DownRouter(), groups)
    assert rows[0]["Check"] == "service error" and notes


def test_chat_goes_straight_to_the_tender_for_tender_questions():
    t = TenderIndex(pages())
    table = parse_boq(FIX / "tender_a_nust_boq.pdf").tables[0]
    r = FakeRouter(good())
    reply = handle_message("how long do bids remain valid? (validity)", table, EditSession(table), r, [], t)
    assert reply.intent == "tender_question" and "**Source:**" in reply.text
    assert len(r.prompts) == 1 and r.prompts[0][0].startswith("You answer questions")


def test_parser_keeps_page_texts():
    result = parse_boq(FIX / "tender_a_nust_boq.pdf")
    assert len(result.page_texts) == 25 and all(isinstance(x, str) for x in result.page_texts)
