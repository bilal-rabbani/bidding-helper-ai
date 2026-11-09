"""Evaluates the BOQ parser against hand-checked answers (the "gold" files).

Run:   python evaluation/run_parser_eval.py [--update-readme]
Writes: evaluation/RESULTS.md, evaluation/results/parser_results.json,
        evaluation/results/parser_cases.csv
Exit code 1 if any target is missed or any critical error is found.
"""
import csv
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.boq_parser import parse_boq          # noqa: E402
from evaluation.probes import PROBES            # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
GOLD = ROOT / "evaluation" / "gold"
RESULTS = ROOT / "evaluation" / "results"

TARGETS = {
    "rows_found": 98.0,
    "quantity": 99.0,
    "unit": 99.0,
    "rate": 99.0,
    "amount": 99.0,
    "verification": 100.0,
    "sections": 95.0,
}


def close(a, b, tol=0.01):
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= tol


def same_text(a, b):
    return (a or "").strip().lower().rstrip(".") == (b or "").strip().lower().rstrip(".")


def pct(num, den):
    return 100.0 if den == 0 else 100.0 * num / den


def evaluate():
    cases, per_tender = [], []
    tot = dict(gold=0, found=0, qty=0, unit=0, rate=0, amount=0, matched=0,
               invented=0, silent_wrong=0, missing_unflagged=0,
               verif_ok=0, verif_n=0, sec_ok=0, sec_n=0, flagged=0)
    for gold_file in sorted(GOLD.glob("*.json")):
        gold = json.loads(gold_file.read_text(encoding="utf-8"))
        pdf = FIXTURES / (gold_file.stem + ".pdf")
        result = parse_boq(pdf)
        for ti, gt in enumerate(gold["tables"]):
            table = result.tables[ti] if ti < len(result.tables) else None
            items = {r.sr_no: r for r in table.items} if table else {}
            gold_rows = {r["sr_no"]: r for r in gt["rows"]}
            tot["gold"] += len(gold_rows)
            t_found = t_ok = 0
            for sr, g in gold_rows.items():
                row = items.get(sr)
                if row is None:
                    miss_flag = bool(table and table.warnings)
                    tot["missing_unflagged"] += 0 if miss_flag else 1
                    cases.append(dict(tender=gold_file.stem, table=gt["name"], sr_no=sr,
                                      found=False, quantity="", unit="", rate="", amount="",
                                      flagged=miss_flag))
                    continue
                tot["found"] += 1; t_found += 1; tot["matched"] += 1
                ok = dict(quantity=close(row.quantity, g["quantity"]),
                          unit=same_text(row.unit, g["unit"]),
                          rate=close(row.rate, g["rate"]),
                          amount=close(row.amount, g["amount"]))
                for k, v in ok.items():
                    tot[{"quantity": "qty"}.get(k, k)] += int(v)
                if all(ok.values()):
                    t_ok += 1
                elif not row.needs_review:
                    tot["silent_wrong"] += 1
                tot["flagged"] += int(row.needs_review)
                cases.append(dict(tender=gold_file.stem, table=gt["name"], sr_no=sr, found=True,
                                  flagged=row.needs_review, **{k: v for k, v in ok.items()}))
            tot["invented"] += len([sr for sr in items if sr not in gold_rows])
            # printed total check
            if table:
                v = table.verification()
                tot["verif_n"] += 1
                good = (v["status"] == gt["expected_verification"]
                        and close(v["printed_total"], gt["printed_total"], 0.01))
                tot["verif_ok"] += int(good)
                names = [r.description for r in table.rows if r.kind == "section"]
                if gt["expected_sections"] or names:
                    tot["sec_n"] += 1
                    tot["sec_ok"] += int(names == gt["expected_sections"])
            per_tender.append(dict(
                tender=gold_file.stem, table=gt["name"], gold_rows=len(gold_rows),
                found=t_found, all_fields_correct=t_ok,
                needs_review=len(table.review_rows) if table else None,
                verification=table.verification()["status"] if table else "table not found",
                printed_total=table.printed_total() if table else None,
                sum_of_rows=table.sum_amount() if table else None))
    probes = {}
    for name, fn in PROBES.items():
        try:
            probes[name] = bool(fn())
        except Exception:
            probes[name] = False
    return cases, per_tender, tot, probes


def build_report(cases, per_tender, tot, probes):
    m = [
        ("Rows found (of hand-checked rows)", pct(tot["found"], tot["gold"]), TARGETS["rows_found"]),
        ("Quantity correct", pct(tot["qty"], tot["matched"]), TARGETS["quantity"]),
        ("Unit correct", pct(tot["unit"], tot["matched"]), TARGETS["unit"]),
        ("Rate correct", pct(tot["rate"], tot["matched"]), TARGETS["rate"]),
        ("Amount correct", pct(tot["amount"], tot["matched"]), TARGETS["amount"]),
        ("Printed total check gives the expected outcome", pct(tot["verif_ok"], tot["verif_n"]),
         TARGETS["verification"]),
        ("Section headings found correctly", pct(tot["sec_ok"], tot["sec_n"]), TARGETS["sections"]),
    ]
    critical = [
        ("Invented rows (not in the tender)", tot["invented"]),
        ("Wrong values NOT flagged for review", tot["silent_wrong"]),
        ("Missing rows with no warning", tot["missing_unflagged"]),
    ]
    all_pass = (all(v >= t for _, v, t in m) and all(c == 0 for _, c in critical)
                and all(probes.values()))
    lines = ["# Parser evaluation", "",
             "Hand-checked answers (gold files) vs. what the parser extracts from three public tenders. "
             "The gold data is a draft made by a second extraction method and "
             "spot-checked by a person (see `evaluation/gold/SPOT_CHECK.md`). "
             "The sample is small (3 tenders, 4 tables), so read the numbers as a rough guide, "
             "not a benchmark.", "",
             "| Metric | Result | Target | |", "|---|---|---|---|"]
    for name, val, tgt in m:
        lines.append(f"| {name} | {val:.1f}% | >= {tgt:g}% | {'pass' if val >= tgt else 'FAIL'} |")
    for name, c in critical:
        lines.append(f"| Critical: {name} | {c} | 0 | {'pass' if c == 0 else 'FAIL'} |")
    lines += [f"| Stress probes passed | {sum(probes.values())} of {len(probes)} | all | "
              f"{'pass' if all(probes.values()) else 'FAIL'} |",
              f"| Rows flagged for review (information) | {tot['flagged']} | info | |", ""]
    lines += ["## Per tender", "",
              "| Tender | Table | Gold rows | Found | All fields correct | Needs review | "
              "Printed total check |", "|---|---|---|---|---|---|---|"]
    for p in per_tender:
        lines.append(f"| {p['tender']} | {p['table']} | {p['gold_rows']} | {p['found']} | "
                     f"{p['all_fields_correct']} | {p['needs_review']} | {p['verification']} |")
    lines += ["", "## Stress probes", "", "| Situation | Result |", "|---|---|"]
    for name, ok in probes.items():
        lines.append(f"| {name} | {'pass' if ok else 'FAIL'} |")
    lines += ["", "## Known limitations", "",
              "- Scanned PDFs have no text layer; they are reported as needing OCR (phase 7).",
              "- Tables without ruled lines may not be found by the table detector.",
              "- When rates are blank the printed total cannot be checked against the rows; "
              "the app says so instead of guessing.",
              "- A tender can contain the same BOQ twice (tender C does: main table and annexure). "
              "Both are reported; deciding which to use is left to the person.",
              "- Description text is not scored automatically; it is checked by eye in the spot check.",
              "- Gold data covers 3 tenders. More tenders will be added as they are collected.",
              "- Until a person has spot-checked the gold files, a 100% score means two "
              "different machine methods agree, not that a human confirmed every row.", ""]
    return "\n".join(lines), m, critical, all_pass


def main():
    cases, per_tender, tot, probes = evaluate()
    report, m, critical, all_pass = build_report(cases, per_tender, tot, probes)
    RESULTS.mkdir(exist_ok=True)
    (ROOT / "evaluation" / "RESULTS.md").write_text(report, encoding="utf-8")
    (RESULTS / "parser_results.json").write_text(json.dumps(
        {"totals": tot, "per_tender": per_tender, "probes": probes, "all_pass": all_pass},
        indent=1), encoding="utf-8")
    with open(RESULTS / "parser_cases.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["tender", "table", "sr_no", "found", "quantity", "unit",
                                          "rate", "amount", "flagged"])
        w.writeheader()
        w.writerows(cases)
    print(report)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(report + "\n")
    if "--update-readme" in sys.argv:
        update_readme(m, critical, probes)
    sys.exit(0 if all_pass else 1)


def update_readme(m, critical, probes):
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    start, end = "<!-- EVAL:START -->", "<!-- EVAL:END -->"
    if start not in text:
        return
    rows = ["| Metric | Result | Target | |", "|---|---|---|---|"]
    for name, val, tgt in m:
        rows.append(f"| {name} | {val:.1f}% | >= {tgt:g}% | {'pass' if val >= tgt else 'FAIL'} |")
    for name, c in critical:
        rows.append(f"| Critical: {name} | {c} | 0 | {'pass' if c == 0 else 'FAIL'} |")
    rows.append(f"| Stress probes passed | {sum(probes.values())} of {len(probes)} | all | "
                f"{'pass' if all(probes.values()) else 'FAIL'} |")
    new = text[:text.index(start) + len(start)] + "\n" + "\n".join(rows) + "\n" + text[text.index(end):]
    readme.write_text(new, encoding="utf-8")


if __name__ == "__main__":
    main()
