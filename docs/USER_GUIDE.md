# Bidding Helper AI - user guide

Bidding Helper AI reads a tender PDF (EPADS format), builds the BOQ, answers questions about the tender and lets you edit rates and download an Excel file. It uses AI services that you reach with **your own free key**, so nobody pays for your use.

## 1. Get your free AI keys (about 5 minutes)

You need at least one key. Groq is a good first choice because its free limits are more generous. Gemini is a good second one.

### Groq
1. Open **console.groq.com/keys** and sign up (Google or email).
2. Click **Create API Key**, give it any name and confirm.
3. Copy the key (it starts with `gsk_`). It is shown only once.

### Gemini (Google)
1. Open **aistudio.google.com/apikey** and sign in with a Google account.
2. Click **Create API key** (choose or create a project when asked).
3. Copy the key (it starts with `AIza`).

### Using your keys
- Paste the key in the matching sidebar box and press **Use and test keys**. A green tick means the key works.
- You can paste several keys in one box, separated by commas. When one key reaches its limit, the app switches to the next one and tells you.
- Keys from different Google accounts have separate limits. Keys made inside the same Google project share one limit.
- Keep keys private. If you think someone saw a key, delete it on the provider's website and create a new one.
- Free limits and model names change from time to time. If a model stops working, choose another one in the sidebar list. The app also tries other models by itself.
- Use only keys you created yourself, and follow each provider's terms.

## 2. Upload a tender
- Click **Upload a tender PDF** in the sidebar. A long tender (100+ pages) can take up to a minute to read.
- It works with PDFs that have selectable text, such as the PDFs downloaded from EPADS. **Scanned PDFs (photos of pages) are not supported yet.**
- Your PDF is read on the server and kept in memory only while your session is open. It is never saved.

## 3. What each tab does
- **Chat:** type what you want in plain words (see the examples below). Every edit is shown as a preview first, and nothing changes until you press **Apply these changes**.
- **BOQ:** the items table. A warning sign marks rows that need review. **Original Rate** is the rate printed in the tender, **Rate** is the one you can change.
- **Needs review:** the doubtful rows, each with its PDF page and the reason.
- **Verification:** compares the sum of the rows with the total printed in the tender. When the rates are blank, it says so instead of guessing.
- **Edit rates:** the same editing as the chat, as a form. You name the rows, choose the change, press **Preview**, then **Apply**. **Undo** reverses the last edit.
- **Tender info:** the **Extract key facts** button (bid security, performance guarantee, dates, eligibility and so on, each with its page and a check) and the list of forms found in the document.
- **Urdu:** translate item descriptions into Urdu, read them next to the English, and correct them. You can set your own glossary of preferred words.
- **Help:** this guide and the known limits.
- **Download Excel (.xlsx)** at the top: a BOQ sheet with live formulas, section subtotals and a grand total, a Summary sheet, and a "BOQ Urdu" sheet when you have translated rows.

## 4. Things to type in the Chat
- Edit rates: `increase items 3 to 5 by 10%`, `reduce all door items by Rs 50`, `set the rate of item 9 to 2500`, `increase the electrical works by 5%`
- Fix a value: `change the unit of item 14 to Sqm`, `quantity of item 6 should be 60`
- Look: `show the rows that need review`, `how many items are there?`, `show the aluminium items`
- Ask about the tender: `what is the bid security?`, `what forms do I need to submit?`, `when is the bid deadline?`, `which PEC category is required?`
- Urdu: `translate items 3 to 5 into Urdu`, `translate all descriptions into Urdu`
- Undo: `undo`

You name rows only by Sr. No (`3, 5, 10-12`), by Ref/Item No (`7-198`), by a word from the description (`door`), or by a section name (`electrical works`). Rows you do not name are never touched.

## 5. Reading the warnings
- **Needs review / warning sign:** the program noticed something odd in a row (for example, text from the page footer mixed into it). Check the PDF page shown.
- **Cannot verify:** the rates are blank in the tender, so the total cannot be checked.
- **Check (key facts):** the AI's exact words were not found on the cited page. Look at the page yourself.
- **Warning under an answer:** the answer could not be tied to the wording of a page. Look at the page before relying on it.
- **Not found:** the tender text does not state it, or the search did not reach it. The app shows the closest pages.

## 6. Save your work
- Use **Save session file** in the sidebar. The file holds your edits, chat, Urdu translations, key facts and the tender text. It never holds your API keys.
- Next time, open the app and use **Continue from a session file**. You do not need to upload the PDF again.
- The file contains your rates, so keep it private. The undo history is not saved.
- If you close or reload the page without saving, your work is lost.

## 7. If something goes wrong
| What you see | What to do |
|---|---|
| "All keys are rate limited" | Wait the time shown, or add another key. Free daily limits can run out. |
| "The model was not found" | Choose another model in the sidebar. The app also tries the next one by itself. |
| The app shows a "wake up" button | Apps sleep after about 12 hours without visitors. Click it and wait a minute. |
| "Oh no" or the page keeps restarting | The free server ran out of memory. Reload, and try a smaller PDF. |
| No BOQ table found | The PDF may be scanned or in a layout the program does not know. Tell the developer. |
| A number looks wrong | Check the PDF page shown in the Needs review tab or in the answer. |

## 8. Before you bid
Bidding Helper AI is a helper, not a replacement for reading the tender. Always check the BOQ, the requirements and the dates against the tender document itself.
