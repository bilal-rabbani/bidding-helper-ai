# Chat evaluation

Models used: groq/openai/gpt-oss-120b

Does the AI turn each sentence into the right action? Rows are compared by which rows get selected. Run with the free Gemini/Groq keys on the NUST test excerpt. 26 sentences; small sample, so treat as a rough guide.

| Metric | Result | Target | |
|---|---|---|---|
| Sentences handled correctly (all) | 100.0% (26/26) | >= 95% | pass |
| Edit sentences turned into the right command | 100.0% | >= 95% | pass |
| Not evaluated (service error or rate limit) | 0 | info | |

Every edit is previewed and needs a click on Apply, so a wrong command cannot change the BOQ silently.

## Each sentence

| Sentence | Result | Detail |
|---|---|---|
| increase the rates of items 3, 5 and 10 to 12 by 10% | pass |  |
| reduce rate for item 7 by 5 percent | pass |  |
| add Rs 50 to the rate of item 4 | pass |  |
| set the rate of item 9 to 2500 | pass |  |
| change the unit of row 14 to Sqm | pass |  |
| quantity of item 6 should be 60 | pass |  |
| raise all aluminium items by 15% | pass |  |
| increase rates for everything with the word door by 8% | pass |  |
| increase the rates of the electrical works by 10% | pass |  |
| decrease civil works rates by 3% | pass |  |
| 7-198 rate up by 20% | pass |  |
| add 10% to items 3 to 5 and the door items | pass |  |
| increase rates by ten percent for items 3 and 4 | pass |  |
| make the rate of item 5 Rs. 3,750.50 | pass |  |
| decrease the rate of items 3 to 5 by Rs 100 | pass |  |
| rename the description of item 3 to Dismantling of partitions | pass |  |
| show me the items that need review | pass |  |
| undo that | pass |  |
| give me the excel | pass |  |
| what forms do I need to submit? | pass |  |
| when is the bid deadline? | pass |  |
| translate the descriptions into urdu | pass |  |
| how many items are there and what is the total? | pass |  |
| what can you do? | pass |  |
| increase the rates by 10% | pass |  |
| delete item 5 | pass |  |
