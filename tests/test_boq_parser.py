"""Phase 1 tests: BOQ parser, stress probes and the evaluation targets."""
from pathlib import Path

import pytest

from core.boq_parser import parse_boq, parse_number
from evaluation.probes import PROBES
from evaluation.run_parser_eval import build_report, evaluate

FIX = Path(__file__).parent / "fixtures"


def test_parse_number_examples():
    assert parse_number("1,234.50") == (1234.5, "")
    assert parse_number("Rs8,847,343.79") == (8847343.79, "")
    assert parse_number("432 Sft") == (432.0, "Sft")
    assert parse_number("-") == (None, "")
    assert parse_number("") == (None, "")
    assert parse_number("abc") == (None, "abc")


@pytest.mark.parametrize("name", list(PROBES), ids=lambda n: n[:50])
def test_stress_probe(name):
    assert PROBES[name]() is True


@pytest.fixture(scope="module")
def parsed():
    return {n: parse_boq(FIX / f"{n}.pdf") for n in
            ("tender_a_nust_boq", "tender_b_jiap_boq", "tender_c_pidcl_boq")}


def test_tender_a(parsed):
    r = parsed["tender_a_nust_boq"]
    assert len(r.tables) == 1
    t = r.tables[0]
    assert len(t.items) == 42
    assert [s.description for s in t.rows if s.kind == "section"] == [
        "A. CIVIL Works", "B. ELECTRICAL Works", "C. HVAC Works"]
    v = t.verification()
    assert v["status"] == "match"
    assert v["printed_total"] == pytest.approx(8847343.79)
    # the row where the page footer ran into the table must be flagged
    row24 = next(i for i in t.items if i.sr_no == 24)
    assert row24.needs_review and row24.amount == pytest.approx(103715.55)


def test_tender_b(parsed):
    t = parsed["tender_b_jiap_boq"].tables[0]
    assert len(t.items) == 5
    assert t.rates_blank
    assert t.items[0].quantity == 432 and t.items[0].unit == "P.Sft"
    assert t.verification()["status"] == "cannot_verify"
    assert t.printed_total() == pytest.approx(3736150)


def test_tender_c(parsed):
    tables = parsed["tender_c_pidcl_boq"].tables
    assert len(tables) == 2
    assert [len(t.items) for t in tables] == [16, 16]
    assert [i.quantity for i in tables[0].items] == [i.quantity for i in tables[1].items]


def test_evaluation_meets_all_targets():
    cases, per_tender, tot, probes = evaluate()
    _, metrics, critical, all_pass = build_report(cases, per_tender, tot, probes)
    assert all_pass, f"targets missed: {metrics} / {critical}"
