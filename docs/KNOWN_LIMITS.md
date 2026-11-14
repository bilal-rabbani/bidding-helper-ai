# Known limits

These come from what was actually found while building and testing the app.

## Tenders it can read
- It was built and tested on **three EPADS tenders** (a renovation, a public-address-rooms job and a solar installation). Tenders from other agencies or in other layouts may not work as well.
- **Scanned PDFs are not supported.** The text must be selectable. OCR is planned for later.
- BOQ tables are found by their ruled lines and column names. Tables without lines, or with unusual column names, may be missed or partly read. When a tender repeats the same BOQ in two places, both are shown and you choose.
- Page numbers: answers show the PDF page and, when it differs, the printed page number from the tender's footer.

## The BOQ
- Rows are read by plain code, not by AI. Doubtful rows are listed under **Needs review** with their page.
- The sum of the rows is checked against the total printed in the tender. When the rates are blank, **the check cannot be done**.
- Rate edits apply only to the rows you name. A row with a blank rate cannot be raised or lowered by a percentage.
- Section names can be used to pick rows, but only if the tender shows its sections as headings in the table.

## Questions about the tender
- The AI answers only from a few passages found by keyword search. If the right passage is not found, the answer can be wrong or "not found". Always look at the cited page.
- Wording that is not in the tender's own words (for example slang) may not find the right pages.
- **Extract key facts** can show "check" or "not found" even when the tender states the fact. Look at the page.
- The list of forms comes from the table of contents and form headings. Which forms you must submit is a question for the Chat, answered from the tender text.
- The test questions and expected answers were written by the developer from three tenders. They are a small sample.

## Urdu translation
- The translation is made by AI. It is a draft that a person must read.
- The built-in glossary is a first draft and not final.
- Numbers and units are checked by the program, but the quality of the Urdu cannot be checked by a program.
- In the Excel file the Urdu uses the font "Urdu Typesetting" (installed with Windows). On other devices a different font appears, still readable.

## Free AI services
- Free keys have small limits. Gemini's free daily allowance per model is small and runs out quickly. Groq's limits are per minute and per day.
- Free model names change and some models listed by a provider cannot be used. The app switches model or key by itself, but it cannot go beyond the limits.
- Answers may differ from one run to another.

## The free hosting
- The app sleeps after about 12 hours without visitors, and the first visitor has to wake it up.
- Memory on the free server is limited. Very large PDFs can make the app restart.
- There are no accounts and nothing is stored on a server. If you close the page without saving a session file, the work is lost.

## Privacy
- Your PDF is read on the app's server and kept only in memory while your session is open.
- To answer a question, the few relevant passages of the tender and your message are sent to Google (Gemini) or Groq with your own key. Their terms apply to that data.
- Session files contain your rates and the tender text. Keep them private.

## Not covered
- Adding or deleting BOQ rows, merging tables, pricing from rate analyses, and other languages besides English and Urdu.
- Any legal, financial or tender-eligibility judgment. Always verify against the tender.
