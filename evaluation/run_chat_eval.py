"""Evaluates the chat: does the AI turn each sentence into the right action? Needs real keys.

Run:  GEMINI_KEYS=... GROQ_KEYS=... python evaluation/run_chat_eval.py
Optional: PRIMARY=groq|gemini, GROQ_MODEL=..., GEMINI_MODEL=..., EVAL_PAUSE=seconds
Rows are compared by WHICH ROWS get selected, so different wording of the same selection is fine.
"""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.boq_edit import EditSession, Selector      # noqa: E402
from core.boq_parser import parse_boq                # noqa: E402
from core.chat import handle_message                 # noqa: E402
from core.llm_router import LLMRouter                # noqa: E402

TARGET = 95.0

CASES = [
    ("increase the rates of items 3, 5 and 10 to 12 by 10%",
     dict(intent="edit", op="percent", field="rate", value=10, rows=dict(numbers="3, 5, 10-12"))),
    ("reduce rate for item 7 by 5 percent",
     dict(intent="edit", op="percent", field="rate", value=-5, rows=dict(numbers="7"))),
    ("add Rs 50 to the rate of item 4",
     dict(intent="edit", op="add", field="rate", value=50, rows=dict(numbers="4"))),
    ("set the rate of item 9 to 2500",
     dict(intent="edit", op="set", field="rate", value=2500, rows=dict(numbers="9"))),
    ("change the unit of row 14 to Sqm",
     dict(intent="edit", op="set", field="unit", value="Sqm", rows=dict(numbers="14"))),
    ("quantity of item 6 should be 60",
     dict(intent="edit", op="set", field="quantity", value=60, rows=dict(numbers="6"))),
    ("raise all aluminium items by 15%",
     dict(intent="edit", op="percent", field="rate", value=15, rows=dict(keywords="aluminium"))),
    ("increase rates for everything with the word door by 8%",
     dict(intent="edit", op="percent", field="rate", value=8, rows=dict(keywords="door"))),
    ("increase the rates of the electrical works by 10%",
     dict(intent="edit", op="percent", field="rate", value=10, rows=dict(section="B."))),
    ("decrease civil works rates by 3%",
     dict(intent="edit", op="percent", field="rate", value=-3, rows=dict(section="A."))),
    ("7-198 rate up by 20%",
     dict(intent="edit", op="percent", field="rate", value=20, rows=dict(item_nos="7-198"))),
    ("add 10% to items 3 to 5 and the door items",
     dict(intent="edit", op="percent", field="rate", value=10, rows=dict(numbers="3-5", keywords="door"))),
    ("increase rates by ten percent for items 3 and 4",
     dict(intent="edit", op="percent", field="rate", value=10, rows=dict(numbers="3, 4"))),
    ("make the rate of item 5 Rs. 3,750.50",
     dict(intent="edit", op="set", field="rate", value=3750.5, rows=dict(numbers="5"))),
    ("decrease the rate of items 3 to 5 by Rs 100",
     dict(intent="edit", op="add", field="rate", value=-100, rows=dict(numbers="3-5"))),
    ("rename the description of item 3 to Dismantling of partitions",
     dict(intent="edit", op="set", field="description", value="Dismantling of partitions",
          rows=dict(numbers="3"))),
    ("show me the items that need review", dict(intent="show_review")),
    ("undo that", dict(intent="undo")),
    ("give me the excel", dict(intent="download")),
    ("what forms do I need to submit?", dict(intent="tender_question")),
    ("when is the bid deadline?", dict(intent="tender_question")),
    ("translate the descriptions into urdu", dict(intent="translate")),
    ("how many items are there and what is the total?", dict(intent="show_summary")),
    ("what can you do?", dict(intent="help")),
    ("increase the rates by 10%", dict(intent=["clarify"])),
    ("delete item 5", dict(intent=["unsupported", "clarify"])),
]


def section_numbers(table, prefix):
    nums = [r.sr_no for r in table.items if r.section.lower().startswith(prefix.lower())]
    return f"{min(nums)}-{max(nums)}"


def selected(table, selector):
    return {r.sr_no for r in table.items if selector.matches(r)}


def expected_rows(table, spec):
    numbers = section_numbers(table, spec["section"]) if "section" in spec else spec.get("numbers", "")
    return selected(table, Selector.from_spec(numbers=numbers, item_nos=spec.get("item_nos"),
                                              keywords=spec.get("keywords")))


def judge(table, expected, reply):
    wanted = expected["intent"] if isinstance(expected["intent"], list) else [expected["intent"]]
    if reply.intent not in wanted:
        return False, f"intent was '{reply.intent}'"
    if wanted != ["edit"]:
        return True, ""
    cmd = reply.command
    if cmd is None:
        return False, "no command"
    if (cmd.op, cmd.field) != (expected["op"], expected["field"]):
        return False, f"op/field was {cmd.op}/{cmd.field}"
    if isinstance(expected["value"], str):
        if str(cmd.value).strip().lower() != expected["value"].lower():
            return False, f"value was {cmd.value!r}"
    elif abs(float(cmd.value) - expected["value"]) > 1e-6:
        return False, f"value was {cmd.value!r}"
    got, want = selected(table, cmd.selector), expected_rows(table, expected["rows"])
    if got != want:
        return False, f"rows differ (missing {sorted(want - got)[:6]}, extra {sorted(got - want)[:6]})"
    return True, ""


def service_error(reply):
    return reply.kind == "error" and reply.intent != "unknown"


def main():
    router = LLMRouter({"gemini": os.environ.get("GEMINI_KEYS", ""), "groq": os.environ.get("GROQ_KEYS", "")})
    if not router.keys:
        sys.exit("No keys found. Set GEMINI_KEYS and/or GROQ_KEYS.")
    for name in router.keys:
        chosen = os.environ.get(name.upper() + "_MODEL")
        if chosen:
            router.set_model(name, chosen)
    router.primary = os.environ.get("PRIMARY") or None
    import core.chat as chat_module
    chat_module.DRY_RUN = True            # never really translate during the test
    table = parse_boq(ROOT / "tests" / "fixtures" / "tender_a_nust_boq.pdf").tables[0]
    session = EditSession(table)

    results, models = [], set()
    for sentence, expected in CASES:
        reply = handle_message(sentence, table, session, router, [])
        if service_error(reply):
            time.sleep(20)                         # a key may be resting - try once more
            reply = handle_message(sentence, table, session, router, [])
        if reply.model:
            models.add(reply.model)
        if service_error(reply):
            results.append(dict(sentence=sentence, status="not evaluated", detail=reply.text[:120]))
        else:
            ok, why = judge(table, expected, reply)
            results.append(dict(sentence=sentence, status="pass" if ok else "FAIL", detail=why))
        time.sleep(float(os.environ.get("EVAL_PAUSE", "3")))

    done = [r for r in results if r["status"] != "not evaluated"]
    passed = [r for r in done if r["status"] == "pass"]
    score = 100.0 * len(passed) / len(done) if done else 0.0
    edit_ids = [s for (s, e) in CASES if e["intent"] == "edit"]
    edits = [r for r in done if r["sentence"] in edit_ids]
    edit_score = 100.0 * sum(r["status"] == "pass" for r in edits) / len(edits) if edits else 0.0

    lines = ["# Chat evaluation", "",
             "Models used: " + (", ".join(sorted(models)) or "unknown"), "",
             "Does the AI turn each sentence into the right action? Rows are compared by which rows "
             "get selected. Run with the free Gemini/Groq keys on the NUST test excerpt. "
             f"{len(CASES)} sentences; small sample, so treat as a rough guide.", "",
             "| Metric | Result | Target | |", "|---|---|---|---|",
             f"| Sentences handled correctly (all) | {score:.1f}% ({len(passed)}/{len(done)}) | >= {TARGET:g}% | "
             f"{'pass' if score >= TARGET else 'FAIL'} |",
             f"| Edit sentences turned into the right command | {edit_score:.1f}% | >= {TARGET:g}% | "
             f"{'pass' if edit_score >= TARGET else 'FAIL'} |",
             f"| Not evaluated (service error or rate limit) | {len(results) - len(done)} | info | |", "",
             "Every edit is previewed and needs a click on Apply, so a wrong command cannot change the BOQ silently.",
             "", "## Each sentence", "", "| Sentence | Result | Detail |", "|---|---|---|"]
    lines += [f"| {r['sentence']} | {r['status']} | {r['detail']} |" for r in results]
    report = "\n".join(lines) + "\n"
    (ROOT / "evaluation" / "RESULTS_CHAT.md").write_text(report, encoding="utf-8")
    (ROOT / "evaluation" / "results").mkdir(exist_ok=True)
    (ROOT / "evaluation" / "results" / "chat_results.json").write_text(
        json.dumps(results, indent=1), encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
