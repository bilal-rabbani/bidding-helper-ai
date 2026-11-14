"""Final checks: nothing private or oversized is tracked, the docs and README are complete."""
import re
import subprocess
from pathlib import Path

import pytest

from core.help_ui import _read

ROOT = Path(__file__).resolve().parent.parent
MAX_BYTES = 5 * 1024 * 1024


@pytest.fixture(scope="module")
def tracked():
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    if out.returncode != 0 or not out.stdout.strip():
        pytest.skip("not a git checkout")
    return [f for f in out.stdout.splitlines() if (ROOT / f).exists()]


def test_no_large_files(tracked):
    big = [f for f in tracked if (ROOT / f).stat().st_size > MAX_BYTES]
    assert big == []


def test_no_private_files_tracked(tracked):
    pdfs = [f for f in tracked if f.lower().endswith(".pdf") and not f.startswith("tests/fixtures/")]
    junk = [f for f in tracked if f.lower().endswith((".xlsx", ".log", ".zip", ".env")) or "private_tenders" in f
            or f in ("cloudflared", "Dockerfile")]
    assert pdfs == [] and junk == []


def test_the_user_guide_explains_the_keys():
    guide = _read("USER_GUIDE.md")
    assert "aistudio.google.com/apikey" in guide and "console.groq.com/keys" in guide
    assert "Scanned PDFs" in guide and "Save session file" in guide


def test_known_limits_are_stated():
    limits = _read("KNOWN_LIMITS.md")
    for topic in ("Scanned PDFs are not supported", "three EPADS tenders", "Urdu", "sleeps", "Privacy"):
        assert topic in limits, topic


def test_readme_is_complete():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for placeholder in ("YOUR-USERNAME", "PASTE-YOUR", "YOUR-APP-LINK"):
        assert placeholder not in readme
    assert "streamlit.app" in readme and "<!-- EVAL:START -->" in readme and "<!-- EVAL:END -->" in readme


def test_readme_links_point_to_files_that_exist():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for target in re.findall(r"\]\(([^)]+)\)", readme):
        if target.startswith(("http://", "https://", "#")):
            continue
        assert (ROOT / target.split("#")[0]).exists(), f"README links to a missing file: {target}"
