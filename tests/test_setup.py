"""Phase 0 tests: the project is set up correctly and test files are safe."""
from pathlib import Path

import pdfplumber
import pytest

from core.settings import load_settings
from scripts.check_no_secrets import scan_project, scan_text

FIXTURES = Path(__file__).parent / "fixtures"
PDFS = sorted(FIXTURES.glob("*.pdf"))


def test_settings_load_and_have_required_sections():
    s = load_settings()
    for key in ("app", "boq_columns", "rate_edit", "llm", "search", "urdu"):
        assert key in s
    assert s["rate_edit"]["decimals"] == 2
    assert s["rate_edit"]["preview_before_apply"] is True
    for col in ("sr_no", "item_no", "description", "unit", "quantity", "rate", "amount"):
        assert s["boq_columns"][col], f"no names listed for column {col}"


def test_three_tender_excerpts_present():
    assert len(PDFS) == 3


@pytest.mark.parametrize("pdf", PDFS, ids=lambda p: p.name)
def test_excerpt_has_text_layer_and_boq_header(pdf):
    with pdfplumber.open(pdf) as doc:
        text = "\n".join((page.extract_text() or "") for page in doc.pages)
    assert len(text) > 500, "no readable text found"
    for word in ("Unit", "Rate", "Amount"):
        assert word in text, f"BOQ header word '{word}' missing"


@pytest.mark.parametrize("pdf", PDFS, ids=lambda p: p.name)
def test_excerpt_has_no_contact_details(pdf):
    """The repo is public, so test files must not carry emails or phone numbers."""
    with pdfplumber.open(pdf) as doc:
        text = "\n".join((page.extract_text() or "") for page in doc.pages)
    assert "@" not in text
    assert "+92" not in text


def test_secret_scanner_detects_fake_keys():
    # Fake keys are assembled at run time so this file itself stays clean.
    fake_google = "AI" + "za" + "A" * 35
    fake_groq = "gsk" + "_" + "a" * 30
    assert scan_text(fake_google)
    assert scan_text(fake_groq)
    assert not scan_text("normal text with no keys")


def test_project_contains_no_secrets():
    assert scan_project() == []
