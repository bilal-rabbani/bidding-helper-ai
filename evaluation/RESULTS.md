# Parser evaluation

Hand-checked answers (gold files) vs. what the parser extracts from three public tenders. The gold data is a draft made by a second extraction method and spot-checked by a person (see `evaluation/gold/SPOT_CHECK.md`). The sample is small (3 tenders, 4 tables), so read the numbers as a rough guide, not a benchmark.

| Metric | Result | Target | |
|---|---|---|---|
| Rows found (of hand-checked rows) | 100.0% | >= 98% | pass |
| Quantity correct | 100.0% | >= 99% | pass |
| Unit correct | 100.0% | >= 99% | pass |
| Rate correct | 100.0% | >= 99% | pass |
| Amount correct | 100.0% | >= 99% | pass |
| Printed total check gives the expected outcome | 100.0% | >= 100% | pass |
| Section headings found correctly | 100.0% | >= 95% | pass |
| Critical: Invented rows (not in the tender) | 0 | 0 | pass |
| Critical: Wrong values NOT flagged for review | 0 | 0 | pass |
| Critical: Missing rows with no warning | 0 | 0 | pass |
| Stress probes passed | 13 of 13 | all | pass |
| Rows flagged for review (information) | 1 | info | |

## Per tender

| Tender | Table | Gold rows | Found | All fields correct | Needs review | Printed total check |
|---|---|---|---|---|---|---|
| tender_a_nust_boq | NUST C3A offices | 42 | 42 | 42 | 1 | match |
| tender_b_jiap_boq | JIAP public address rooms | 5 | 5 | 5 | 0 | cannot_verify |
| tender_c_pidcl_boq | PIDCL main table | 16 | 16 | 16 | 0 | cannot_verify |
| tender_c_pidcl_boq | PIDCL annexure BOQ | 16 | 16 | 16 | 0 | cannot_verify |

## Stress probes

| Situation | Result |
|---|---|
| Row description split across two pages is joined and flagged | pass |
| Missing row number is reported | pass |
| Unreadable quantity is flagged | pass |
| Amount that differs from quantity x rate is flagged | pass |
| Repeated header row inside a table is ignored | pass |
| Page footer text mixed into a row is cleaned and flagged | pass |
| Unit written inside the quantity cell ('432 Sft') | pass |
| Other column spellings (S.No., Qty., Rate (PKR)) | pass |
| Total rows are not counted as items | pass |
| Table continued on a page without a header row | pass |
| Tables that are not a BOQ are ignored | pass |
| Two jobs in one tender give two separate tables | pass |
| Numbers like 1,234.50, Rs8,847,343.79 and '-' are read correctly | pass |

## Known limitations

- Scanned PDFs have no text layer; they are reported as needing OCR (phase 7).
- Tables without ruled lines may not be found by the table detector.
- When rates are blank the printed total cannot be checked against the rows; the app says so instead of guessing.
- A tender can contain the same BOQ twice (tender C does: main table and annexure). Both are reported; deciding which to use is left to the person.
- Description text is not scored automatically; it is checked by eye in the spot check.
- Gold data covers 3 tenders. More tenders will be added as they are collected.
- Until a person has spot-checked the gold files, a 100% score means two different machine methods agree, not that a human confirmed every row.
