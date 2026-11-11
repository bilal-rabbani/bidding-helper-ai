"""Reads the whole tender text into searchable passages. Keyword search (BM25), no AI needed."""
import math
import re
from collections import Counter
from dataclasses import dataclass

PAGE_MARK = re.compile(r"Page\s+(\d+)\s+of\s+(\d+)", re.I)
FOOTER_START = "e-Pak Acquisition and Disposal System"
MAX_CHARS = 900
MIN_CHARS = 30
TOC_HEADINGS = 6          # a page with this many headings is a table of contents
TOC = "Table of contents"

STOP = set("""a an the of to in on for and or is are be was were it its this that these those with by as at
from shall will may must can any all not no if into than then which who whom what when where how do does did
have has had their there such other under per etc please tell me give show i we you your our""".split())


# ------------------------------------------------------------------ page numbers
def printed_pages(page_texts) -> list:
    """The printed page number of every PDF page (from 'Page X of Y'), or None when unknown."""
    marks = {}
    for i, text in enumerate(page_texts, start=1):
        found = PAGE_MARK.findall(text or "")
        if found:
            marks[i] = int(found[-1][0])
    if not marks:
        return [None] * len(page_texts)
    known, out = sorted(marks), []
    for i in range(1, len(page_texts) + 1):
        if i in marks:
            out.append(marks[i])
            continue
        near = min(known, key=lambda k: abs(k - i))
        guess = i - (near - marks[near])
        out.append(guess if abs(near - i) <= 3 and guess >= 1 else None)
    return out


def page_label(pdf_page, printed) -> str:
    """'p.12' when the numbers agree, else 'PDF p.12 (printed p.9)'."""
    if printed is None or printed == pdf_page:
        return f"p.{pdf_page}"
    return f"PDF p.{pdf_page} (printed p.{printed})"


# ------------------------------------------------------------------ headings and passages
HEADINGS = [re.compile(p) for p in (
    r"^(?:SECTION|Section)\s+[IVXLC]+\b.*",
    r"^(?:Form|FORM)\s+[A-Za-z0-9][A-Za-z0-9.\-() ]{0,28}(?::.*)?$",
    r"^(?:ANNEXURE|Annexure|ANNEX|Annex)\b.{0,70}$",
    r"^(?:Bid Data Sheet|Eligibility Criteria|Evaluation Criteria|Instructions to Bidders|Invitation for Bids|"
    r"Special Conditions of Contract|General Conditions of Contract|Qualification Criteria|Contract Forms)\b.{0,60}$",
)]


def heading_of(line):
    t = " ".join((line or "").split())
    if not t or len(t) > 100:
        return None
    return t if any(p.match(t) for p in HEADINGS) else None


@dataclass
class Passage:
    id: int
    pdf_page: int
    printed_page: object
    section: str
    text: str


def _flush(passages, buf, pno, printed, section, pid):
    body = " ".join(buf).strip()
    if len(body) >= MIN_CHARS:
        passages.append(Passage(pid, pno, printed[pno - 1], section, body))
        pid += 1
    return pid


def build_passages(page_texts, printed) -> list:
    passages, section, pid = [], "(start of document)", 0
    for pno, text in enumerate(page_texts, start=1):
        lines = [" ".join(l.split()) for l in (text or "").splitlines()]
        lines = [l for l in lines if l and not l.startswith(FOOTER_START)]
        toc = sum(1 for l in lines if heading_of(l)) >= TOC_HEADINGS
        buf, size = [], 0
        for line in lines:
            heading = None if toc else heading_of(line)
            if heading:
                pid = _flush(passages, buf, pno, printed, TOC if toc else section, pid)
                buf, size = [], 0
                section = heading
            if size + len(line) > MAX_CHARS and buf:
                keep = buf[-1:]                                  # one line of overlap
                pid = _flush(passages, buf, pno, printed, TOC if toc else section, pid)
                buf, size = list(keep), sum(len(x) + 1 for x in keep)
            buf.append(line)
            size += len(line) + 1
        pid = _flush(passages, buf, pno, printed, TOC if toc else section, pid)
    return passages


FORM_LINE = re.compile(
    r"^((?:Form|FORM|Annexure|ANNEXURE|Annex)\s+[A-Za-z0-9][A-Za-z0-9.\-() ]{0,25}?)\s*(?::\s*(.{3,90}))?$")


def find_forms(page_texts, printed) -> list:
    """Every form or annexure heading in the document (code only, no AI)."""
    forms, seen = [], set()
    for pno, text in enumerate(page_texts, start=1):
        lines = [" ".join(l.split()) for l in (text or "").splitlines()]
        if sum(1 for l in lines if heading_of(l)) >= TOC_HEADINGS:
            continue
        for line in lines:
            m = FORM_LINE.match(line)
            if not m or len(line) > 100:
                continue
            label = re.sub(r"\s*\(cont\.?\)\s*$", "", m.group(1), flags=re.I).strip()
            key = re.sub(r"[^a-z0-9]", "", label.lower())
            if key in seen:
                continue
            seen.add(key)
            forms.append({"label": label, "title": (m.group(2) or "").strip(),
                          "pdf_page": pno, "printed_page": printed[pno - 1]})
    return forms


# ------------------------------------------------------------------ search
def tokenize(text) -> list:
    out = []
    for w in re.findall(r"[a-z0-9]+", (text or "").lower()):
        if w in STOP or (len(w) < 2 and not w.isdigit()):
            continue
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.append(w)
    return out


EXPANSIONS = [
    (r"bid security|earnest|security deposit", "bid security earnest money bid securing declaration pay order bank guarantee"),
    (r"performance (?:guarantee|security)", "performance guarantee performance security percent"),
    (r"deadline|submission|submit|closing|last date", "deadline submission closing date time bids received"),
    (r"open(?:ed|ing)?\b", "bid opening opened date time"),
    (r"validity|valid for|remain valid", "bid validity period days remain valid"),
    (r"\bfee\b|cost of (?:the )?(?:bidding )?document", "tender fee cost of bidding document pay order"),
    (r"eligib|qualif|requirement", "eligibility qualification criteria registration experience turnover"),
    (r"\bpec\b|registration|licen[cs]e", "pec registration category license specialization code"),
    (r"\bforms?\b|document|annex|checklist|submit", "form annexure declaration undertaking affidavit certificate checklist documents comprising bid"),
    (r"complet|duration|period", "completion period time for completion days months"),
    (r"liquidated|penalt|delay", "liquidated damages delay per day"),
    (r"advance|mobili", "advance payment mobilization"),
    (r"payment|invoice|certificate", "payment interim payment certificate"),
    (r"retention", "retention money"),
    (r"warrant|defects?", "defects liability period"),
    (r"joint venture|consortium|\bjv\b", "joint venture consortium association"),
    (r"experience|similar", "experience similar works completed"),
    (r"turnover|financial", "turnover financial capacity bank statement"),
    (r"\btax|\bntn|\bfbr", "tax ntn fbr registration active taxpayer"),
]


def expand_query(query: str) -> str:
    extra = [add for pattern, add in EXPANSIONS if re.search(pattern, query, re.I)]
    return query + " " + " ".join(extra)


class BM25:
    def __init__(self, docs_tokens, k1=1.4, b=0.75):
        self.k1, self.b = k1, b
        self.tf = [Counter(d) for d in docs_tokens]
        self.len = [len(d) for d in docs_tokens]
        self.avg = (sum(self.len) / len(self.len)) if self.len else 0.0
        df = Counter()
        for c in self.tf:
            df.update(c.keys())
        n = len(docs_tokens)
        self.idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def scores(self, weights: dict) -> list:
        out = [0.0] * len(self.tf)
        for term, w in weights.items():
            idf = self.idf.get(term)
            if idf is None:
                continue
            for i, c in enumerate(self.tf):
                f = c.get(term, 0)
                if f:
                    denom = f + self.k1 * (1 - self.b + self.b * self.len[i] / (self.avg or 1.0))
                    out[i] += w * idf * f * (self.k1 + 1) / denom
        return out


class TenderIndex:
    def __init__(self, page_texts):
        self.page_texts = [t or "" for t in page_texts]
        self.printed = printed_pages(self.page_texts)
        self.passages = build_passages(self.page_texts, self.printed)
        self.forms = find_forms(self.page_texts, self.printed)
        self.searchable = [p for p in self.passages if p.section != TOC]
        self._bm25 = BM25([tokenize(p.section + " " + p.section + " " + p.text) for p in self.searchable])

    @property
    def n_pages(self) -> int:
        return len(self.page_texts)

    def search(self, query: str, k: int = 6) -> list:
        weights = {t: 2.0 for t in tokenize(query)}
        for t in tokenize(expand_query(query)):
            weights.setdefault(t, 1.0)
        scores = self._bm25.scores(weights)
        order = sorted(range(len(scores)), key=lambda i: -scores[i])
        return [self.searchable[i] for i in order[:k] if scores[i] > 0]
