"""Fails if an API key or password-like string is found in the project files.

Run:  python scripts/check_no_secrets.py
Because this repository is public, a leaked key would be visible to everyone.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PATTERNS = {
    "Google/Gemini API key": r"AIza[0-9A-Za-z_\-]{35}",
    "Groq API key": r"gsk_[A-Za-z0-9]{20,}",
    "Anthropic API key": r"sk-ant-[A-Za-z0-9_\-]{20,}",
    "OpenAI-style API key": r"sk-[A-Za-z0-9]{32,}",
    "GitHub token": r"gh[pousr]_[A-Za-z0-9]{30,}",
    "JWT / Supabase key": r"eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}",
    "Private key block": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
}

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "venv", ".venv", "private_tenders"}
SKIP_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".xlsx", ".zip", ".pyc"}


def scan_text(text: str) -> list:
    """Return the names of the secret types found in a piece of text."""
    return [name for name, pat in PATTERNS.items() if re.search(pat, text)]


def scan_project(root: Path = ROOT) -> list:
    problems = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for name in scan_text(text):
            problems.append(f"{path.relative_to(root)}: looks like a {name}")
    return problems


if __name__ == "__main__":
    found = scan_project()
    if found:
        print("SECRET CHECK FAILED:")
        for line in found:
            print("  -", line)
        sys.exit(1)
    print("Secret check passed: no keys found.")
