"""Saving and loading a work session as one JSON file (no accounts, nothing stored on a server).

The file holds the BOQ tables with every edit, the Urdu translations, the chat, the key facts and the
text of the tender pages. It never holds API keys.
"""
import json
from dataclasses import dataclass, fields
from datetime import datetime, timezone

from core.boq_edit import EditSession
from core.boq_parser import BOQRow, BOQTable, ParseResult
from core.tender_index import TenderIndex

FORMAT = "bidding-helper-ai-session"
VERSION = 1
MAX_CHAT = 200
ROW_FIELDS = {f.name for f in fields(BOQRow)}
EXTRA_ROW_FIELDS = ("description_ur", "description_ur_src", "urdu_check")     # added by the Urdu feature


class SessionFileError(ValueError):
    """The file cannot be used. The message says why in plain words."""


@dataclass
class SessionData:
    result: ParseResult
    sessions: list
    tender: object
    chat: list
    key_facts: object
    file_name: str
    saved_at: str


# ------------------------------------------------------------------ saving
def _table_to_dict(t) -> dict:
    return {"job": t.job, "pages": list(t.pages), "columns": list(t.columns),
            "warnings": list(t.warnings), "totals": [dict(x) for x in t.totals],
            "urdu_glossary": getattr(t, "urdu_glossary", None),
            "rows": [dict(r.__dict__) for r in t.rows]}


def to_session_bytes(result, file_name="", chat=None, key_facts=None) -> bytes:
    payload = {
        "format": FORMAT,
        "version": VERSION,
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "file_name": file_name or "",
        "warnings": list(result.warnings),
        "page_texts": list(result.page_texts),
        "tables": [_table_to_dict(t) for t in result.tables],
        "chat": [m for m in (chat or [])[-MAX_CHAT:] if isinstance(m, dict)],
        "key_facts": key_facts,
    }
    return json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")


# ------------------------------------------------------------------ loading
def _row_from_dict(d) -> BOQRow:
    if not isinstance(d, dict):
        raise TypeError("row is not an object")
    row = BOQRow(**{k: v for k, v in d.items() if k in ROW_FIELDS})
    for name in EXTRA_ROW_FIELDS:
        if name in d:
            setattr(row, name, d[name])
    return row


def _table_from_dict(d) -> BOQTable:
    table = BOQTable(job=str(d["job"]), pages=[int(p) for p in d.get("pages", [])],
                     columns=list(d.get("columns", [])), warnings=[str(w) for w in d.get("warnings", [])],
                     totals=[dict(x) for x in d.get("totals", [])])
    table.rows = [_row_from_dict(r) for r in d["rows"]]
    if d.get("urdu_glossary"):
        table.urdu_glossary = str(d["urdu_glossary"])
    return table


def load_session(raw: bytes) -> SessionData:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise SessionFileError("This is not a session file (it could not be read as text).")
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise SessionFileError("This file is not a Bidding Helper AI session file.")
    try:
        version = int(data.get("version", 0))
    except (TypeError, ValueError):
        raise SessionFileError("The session file is damaged (no version number).")
    if version > VERSION:
        raise SessionFileError("This session file was made by a newer version of the app. Please update the app.")
    try:
        tables = [_table_from_dict(t) for t in data["tables"]]
        page_texts = [str(x) for x in data.get("page_texts", [])]
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        raise SessionFileError(f"The session file is damaged ({type(e).__name__}).")
    result = ParseResult(tables=tables, warnings=[str(w) for w in data.get("warnings", [])],
                         page_texts=page_texts)
    chat = [m for m in data.get("chat", []) if isinstance(m, dict)
            and m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)]
    facts = data.get("key_facts")
    facts = facts if isinstance(facts, dict) and isinstance(facts.get("rows"), list) else None
    return SessionData(result=result, sessions=[EditSession(t) for t in tables],
                       tender=TenderIndex(page_texts) if page_texts else None, chat=chat,
                       key_facts=facts, file_name=str(data.get("file_name", "")),
                       saved_at=str(data.get("saved_at", "")))
