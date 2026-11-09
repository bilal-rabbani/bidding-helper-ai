# Bug report - phase 1 (BOQ parser)

## Found and fixed while building

| # | What happened | Where | Fix |
|---|---|---|---|
| 1 | The EPADS page footer ("Acquisition and Disposal System (EPADS) generated document ... Page") runs into the last table row of a page. Letters from it landed inside the Sr. No, Ref No. and Amount cells, and the table had a different number of columns than its header. | Tender A, excerpt page 12 (row 24) | The parser reads the leading number of each cell, removes footer fragments from the Ref No., and flags the row as **needs review**. Row 24's values are confirmed by quantity x rate = amount (45 x 2,304.79 = 103,715.55). |
| 2 | "Total" and "GRAND TOTAL" rows were wrongly flagged as footer noise. | All tenders | Footer checks now apply to item rows only. |
| 3 | A quantity like "as per note" was reported as footer noise instead of simply "quantity could not be read". | Probe 3 | Quantity text no longer counts as footer noise. |
| 4 | The gold-draft script could not read section names and the grand total because the PDF text layout wraps them over two lines. | `make_gold_draft.py` | Section names are typed in the script; total pattern handles the wrap. |

## Open observations (not bugs, but you should know)

1. **Tender C contains the BOQ twice**: the main table (16 items) and an annexure BOQ (the same 16 items with slightly different descriptions). The parser reports both as separate tables. Which one to use is your decision.
2. **Tenders B and C print a total although the rates are blank** (Rs 3,736,150 and Rs 12,627,950; probably the engineer's estimate). The sum of the rows cannot be checked against it, so the app shows "cannot verify" and displays the printed total as information.
3. **The footer problem was seen on one page only.** Other tenders may mix text into the table in other ways; the parser flags rows whose column count or cell contents look wrong, but this needs more tenders to test.
4. **Gold data is a draft.** Until `evaluation/gold/SPOT_CHECK.md` is checked by a person, 100% means two machine methods agree.
