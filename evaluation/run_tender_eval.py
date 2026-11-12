"""Evaluates tender questions on the FULL tender PDFs (kept in Google Drive, not in the repo).

Run: TENDER_DIR=/content/drive/MyDrive/tenders [GEMINI_KEYS=... GROQ_KEYS=...] python evaluation/run_tender_eval.py
Without keys only the search step is scored (no AI needed).
"""
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.llm_router import LLMRouter                # noqa: E402
from core.pdf_reader import read_pages               # noqa: E402
from core.tender_index import TenderIndex            # noqa: E402
from core.tender_qa import answer_question           # noqa: E402

TARGET_SEARCH, TARGET_ANSWER = 90.0, 85.0


def norm(s):
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


def pct(a, b):
    return 100.0 * a / b if b else 0.0


def main():
    gold = json.loads((ROOT / "evaluation" / "gold" / "tender_questions.json").read_text(encoding="utf-8"))
    folder = Path(os.environ.get("TENDER_DIR", "/content/drive/MyDrive/tenders"))
    router = LLMRouter({"gemini": os.environ.get("GEMINI_KEYS", ""), "groq": os.environ.get("GROQ_KEYS", "")})
    router.primary = os.environ.get("PRIMARY") or None
    use_ai = bool(router.keys) and os.environ.get("USE_AI", "1") == "1"
    pause = float(os.environ.get("EVAL_PAUSE", "6"))

    rows, stats = [], []
    s_hit = s_n = a_ok = a_n = invented = neg_n = unverified = 0
    indexes = {}
    for key, t in gold["tenders"].items():
        pdf = folder / t["file"]
        if not pdf.exists():
            print("MISSING:", pdf)
            continue
        idx = TenderIndex([p.text for p in read_pages(pdf)])
        indexes[key] = idx
        stats.append(f"| {t['label']} | {idx.n_pages} | {len(idx.passages)} | "
                     f"{sum(1 for p in idx.printed if p is not None)} | {len(idx.forms)} |")
        for q in t["questions"]:
            hit = any(p.pdf_page in q["pages"] for p in idx.search(q["q"], 6))
            s_n += 1
            s_hit += int(hit)
            answer, detail = "-", ""
            if use_ai:
                a = answer_question(q["q"], idx, router)
                time.sleep(pause)
                if a.text.startswith("I could not reach"):
                    answer, detail = "not evaluated", a.text[:90]
                else:
                    a_n += 1
                    text_ok = any(norm(e) in norm(a.answer) for e in q["expect_any"])
                    page_ok = any(pg in q["pages"] for pg in a.pages)
                    ok = a.found and text_ok and page_ok
                    a_ok += int(ok)
                    unverified += int(a.found and not a.verified)
                    answer = "pass" if ok else "FAIL"
                    detail = "" if ok else f"found={a.found} text_ok={text_ok} page_ok={page_ok} cited={a.pages}"
            rows.append((t["label"], q["q"], "hit" if hit else "MISS", answer, detail))
    if use_ai and indexes:
        first = next(iter(indexes.values()))
        for q in gold["negative"]:
            a = answer_question(q, first, router)
            time.sleep(pause)
            if a.text.startswith("I could not reach"):
                continue
            neg_n += 1
            invented += int(a.found)
            rows.append(("(negative)", q, "-", "pass" if not a.found else "INVENTED", a.answer[:80]))

    lines = ["# Tender question evaluation", "",
             "Questions about the full tenders (kept outside the repo). Search = is the right PDF page among "
             "the 6 passages sent to the AI. Answer = the expected words are in the answer AND the cited page "
             "is a right one. Small sample; the expected answers are a draft until a person has verified them.", "",
             "| Metric | Result | Target | |", "|---|---|---|---|",
             f"| Search finds the right page | {pct(s_hit, s_n):.1f}% ({s_hit}/{s_n}) | >= {TARGET_SEARCH:g}% | "
             f"{'pass' if pct(s_hit, s_n) >= TARGET_SEARCH else 'FAIL'} |"]
    if use_ai:
        lines += [f"| Answers correct with the right page | {pct(a_ok, a_n):.1f}% ({a_ok}/{a_n}) | >= {TARGET_ANSWER:g}% | "
                  f"{'pass' if pct(a_ok, a_n) >= TARGET_ANSWER else 'FAIL'} |",
                  f"| Critical: answers invented when the tender says nothing | {invented} of {neg_n} | 0 | "
                  f"{'pass' if invented == 0 else 'FAIL'} |",
                  f"| Answers whose quote could not be matched to the page (information) | {unverified} | info | |"]
    else:
        lines.append("| Answers | not run (no keys) | | |")
    lines += ["", "## Documents", "", "| Tender | Pages | Passages | Pages with printed number | Forms found |",
              "|---|---|---|---|---|"] + stats
    lines += ["", "## Each question", "", "| Tender | Question | Search | Answer | Detail |", "|---|---|---|---|---|"]
    lines += [f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} |" for r in rows]
    report = "\n".join(lines) + "\n"
    (ROOT / "evaluation" / "RESULTS_TENDER.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
