"""Urdu translation of BOQ item descriptions.

The AI translates. Plain code decides which rows to translate, gives the AI the glossary
words that apply, and checks every translation (numbers kept, glossary words used).
"""
import re

from core.llm_router import AllKeysFailed, LLMError
from core.tender_qa import extract_json

DEFAULT_GLOSSARY = """# english = urdu   (one per line; lines starting with # are ignored)
# This is a first draft. Correct any word you prefer in the Urdu tab of the app.
partition = پارٹیشن
partitions = پارٹیشنز
cement = سیمنٹ
cement board = سیمنٹ بورڈ
plaster = پلستر
painting = رنگ کاری
paint = رنگ
distemper = ڈسٹیمپر
emulsion = ایمولشن
tile = ٹائل
tiles = ٹائلیں
flooring = فرش
marble = سنگ مرمر
granite = گرینائٹ
concrete = کنکریٹ
brickwork = اینٹوں کی چنائی
brick = اینٹ
masonry = چنائی
excavation = کھدائی
backfilling = بھرائی
reinforcement = سریا
steel = اسٹیل
aluminium = ایلومینیم
glass = شیشہ
door = دروازہ
doors = دروازے
window = کھڑکی
windows = کھڑکیاں
wall = دیوار
walls = دیواریں
false ceiling = فالس سیلنگ
ceiling = سیلنگ
roof = چھت
wiring = وائرنگ
cable = کیبل
conduit = کنڈیوٹ
switch = سوئچ
socket = ساکٹ
light = لائٹ
lights = لائٹس
fan = پنکھا
air conditioner = ایئر کنڈیشنر
pipe = پائپ
sanitary = سینیٹری
solar panel = سولر پینل
solar panels = سولر پینلز
inverter = انورٹر
battery = بیٹری
supply = فراہمی
providing = فراہمی
fixing = تنصیب
installation = تنصیب
testing = ٹیسٹنگ
commissioning = کمیشننگ
dismantling = اکھاڑنا
taking down = اتارنا
including = بشمول
complete = مکمل
as per = کے مطابق
thickness = موٹائی
height = اونچائی
width = چوڑائی
length = لمبائی
lump sum = یکمشت
"""

UR_SYSTEM = r"""You translate item descriptions of a bill of quantities (BOQ) from English into Urdu for a construction tender in Pakistan. Output ONE JSON object and nothing else:
{"translations": [{"n": 1, "urdu": "..."}]}
Rules:
- One entry per numbered description, in order, with its number in "n".
- Use clear, formal Urdu as written in Pakistani construction documents.
- Keep numbers, dimensions, units (mm, m, Sqm, Rft, Nos), grades, brand and model names, codes and abbreviations exactly as written, in Latin letters and Western digits.
- When a GLOSSARY is given, use its Urdu word whenever the English term appears.
- Do not add, remove or explain anything. Translate the whole description."""


# ------------------------------------------------------------------ glossary
def parse_glossary(text) -> dict:
    """'door = دروازہ' lines -> {'door': 'دروازہ'}."""
    out = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        english, urdu = (x.strip() for x in line.split("=", 1))
        if english and urdu:
            out[english.lower()] = urdu
    return out


def glossary_for(descriptions, glossary) -> dict:
    """Only the glossary terms that really appear in these descriptions (whole words)."""
    text = " ".join(descriptions).lower()
    return {e: u for e, u in glossary.items()
            if re.search(r"(?<![a-z0-9])" + re.escape(e) + r"(?![a-z0-9])", text)}


# ------------------------------------------------------------------ checks
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def has_urdu(text) -> bool:
    return bool(re.search(r"[\u0600-\u06FF]", text or ""))


def _squash(text) -> str:
    return re.sub(r"[\s\u200c\u200d]+", "", text or "")


def _problems(english, urdu, terms) -> str:
    """What looks wrong with a translation ('' when nothing does)."""
    problems = []
    ur_digits = urdu.translate(_DIGITS).replace(",", "")
    missing = [n for n in re.findall(r"\d+(?:\.\d+)?", english.replace(",", "")) if n not in ur_digits]
    if missing:
        problems.append("numbers not kept: " + ", ".join(dict.fromkeys(missing[:4])))
    squashed = _squash(urdu)
    absent = [e for e, u in terms.items() if _squash(u) not in squashed]
    if absent:
        problems.append("glossary word not used: " + ", ".join(absent[:3]))
    if len(re.findall(r"[A-Za-z]", urdu)) > len(re.findall(r"[\u0600-\u06FF]", urdu)):
        problems.append("mostly English")
    return "; ".join(problems)


# ------------------------------------------------------------------ storage on the rows
def urdu_for(row) -> str:
    """The Urdu text, only while the English description is still the one that was translated."""
    if getattr(row, "description_ur_src", None) != row.description:
        return ""
    return getattr(row, "description_ur", "") or ""


def urdu_check_for(row) -> str:
    return getattr(row, "urdu_check", "") if urdu_for(row) else ""


def set_urdu(row, text, check="") -> None:
    row.description_ur = text.strip()
    row.description_ur_src = row.description
    row.urdu_check = check


# ------------------------------------------------------------------ translating
def build_prompt(batch, terms) -> str:
    parts = []
    if terms:
        listed = "\n".join(f"{e} = {u}" for e, u in sorted(terms.items(), key=lambda kv: -len(kv[0])))
        parts.append("GLOSSARY:\n" + listed)
    parts.append("DESCRIPTIONS:\n" + "\n".join(
        f"{i}. {r.description[:700]}" for i, r in enumerate(batch, start=1)))
    return "\n\n".join(parts) + "\n\nJSON:"


def translate_rows(rows, router, glossary=None, batch_size=6, force=False):
    """Translate the descriptions of these rows. Returns (stats, notes)."""
    glossary = parse_glossary(DEFAULT_GLOSSARY) if glossary is None else glossary
    todo = [r for r in rows if force or not urdu_for(r)]
    stats = {"asked": len(todo), "done": 0, "check": 0, "failed": 0}
    notes = []
    for start in range(0, len(todo), batch_size):
        batch = todo[start:start + batch_size]
        terms = glossary_for([r.description for r in batch], glossary)
        try:
            res = router.complete(build_prompt(batch, terms), system=UR_SYSTEM,
                                  temperature=0.1, max_tokens=4000)
        except LLMError as e:
            notes.append(f"Could not reach the AI service: {e}")
            stats["failed"] += len(todo) - start
            break
        notes += list(getattr(res, "notes", []) or [])
        by_n = {}
        for item in (extract_json(res.text) or {}).get("translations") or []:
            try:
                by_n[int(item.get("n"))] = str(item.get("urdu") or "").strip()
            except (TypeError, ValueError, AttributeError):
                continue
        for n, row in enumerate(batch, start=1):
            urdu = by_n.get(n, "")
            if not urdu or not has_urdu(urdu):
                stats["failed"] += 1
                continue
            check = _problems(row.description, urdu, terms)
            set_urdu(row, urdu, check)
            stats["done"] += 1
            stats["check"] += int(bool(check))
    return stats, notes
