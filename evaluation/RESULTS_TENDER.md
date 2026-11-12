# Tender question evaluation

Questions about the full tenders (kept outside the repo). Search = is the right PDF page among the 6 passages sent to the AI. Answer = the expected words are in the answer AND the cited page is a right one. Small sample; the expected answers are a draft until a person has verified them.

| Metric | Result | Target | |
|---|---|---|---|
| Search finds the right page | 100.0% (15/15) | >= 90% | pass |
| Answers correct with the right page | 93.3% (14/15) | >= 85% | pass |
| Critical: answers invented when the tender says nothing | 0 of 2 | 0 | pass |
| Answers whose quote could not be matched to the page (information) | 1 | info | |

## Documents

| Tender | Pages | Passages | Pages with printed number | Forms found |
|---|---|---|---|---|
| NUST C3A renovation | 128 | 228 | 125 | 18 |
| JIAP public address rooms | 128 | 304 | 125 | 6 |
| PIDCL 50 kW solar | 80 | 161 | 78 | 6 |

## Each question

| Tender | Question | Search | Answer | Detail |
|---|---|---|---|---|
| NUST C3A renovation | How long must bids remain valid? | hit | pass |  |
| NUST C3A renovation | What is the performance guarantee? | hit | pass |  |
| NUST C3A renovation | What is the bid security and in what form is it paid? | hit | pass |  |
| NUST C3A renovation | What is the tender fee? | hit | pass |  |
| NUST C3A renovation | When will the bids be opened? | hit | pass |  |
| JIAP public address rooms | How long must bids remain valid? | hit | pass |  |
| JIAP public address rooms | What is the performance guarantee? | hit | FAIL | found=True text_ok=True page_ok=False cited=[63] |
| JIAP public address rooms | Which PEC registration category is required? | hit | pass |  |
| JIAP public address rooms | When will the bids be opened? | hit | pass |  |
| JIAP public address rooms | In what form can the bid security be paid? | hit | pass |  |
| PIDCL 50 kW solar | How long must bids remain valid? | hit | pass |  |
| PIDCL 50 kW solar | What is the performance guarantee? | hit | pass |  |
| PIDCL 50 kW solar | Which PEC registration category is required? | hit | pass |  |
| PIDCL 50 kW solar | Which specialization code is required on the PEC license? | hit | pass |  |
| PIDCL 50 kW solar | When will the bids be opened? | hit | pass |  |
| (negative) | What is the favourite colour of the procurement officer? | - | pass |  |
| (negative) | How many camels does the contractor have to supply? | - | pass |  |
