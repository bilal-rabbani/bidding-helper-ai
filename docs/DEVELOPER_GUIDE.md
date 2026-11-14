# Developer guide

## How the project is organised
- `app.py` - the Streamlit screen.
- `core/` - the logic: `boq_parser.py` (finds and reads BOQ tables), `boq_edit.py` (selecting rows, rate edits, undo), `excel_export.py`, `chat.py` and `chat_ui.py`, `tender_index.py` and `tender_qa.py` (search, answers, key facts, forms), `urdu.py` and `urdu_ui.py`, `llm_router.py` (Gemini and Groq with several keys), `session_file.py` and `session_ui.py`, `help_ui.py`.
- `config/settings.yaml` - column-name variants, rounding, default models.
- `tests/` - automatic tests (no API keys needed). `tests/fixtures/` holds small BOQ-page excerpts of public tenders.
- `evaluation/` - accuracy reports and the hand-checked answers they compare with.
- `docs/` - user guide, known limits, this guide, roadmap.

## Working in Colab
1. Open a Colab notebook and download the project: `git clone https://github.com/bilal-rabbani/bidding-helper-ai.git`, then `cd` into it.
2. Install the libraries: `pip install -r requirements-dev.txt`.
3. Make changes, run the tests with `python -m pytest -q`, then push.
4. Colab erases its files when a session ends. **Push after every working session.** After a reset, clone again and reinstall.
5. Secrets (Colab key icon): `GITHUB_TOKEN`, `GEMINI_KEYS`, `GROQ_KEYS` (several keys separated by commas). Never paste keys into code or notebooks.
6. Full tenders for evaluation live in Google Drive (`MyDrive/tenders`), never in the repository.

## Tests and evaluations
- `python -m pytest -q` - all tests (GitHub runs them on every push).
- `python evaluation/run_parser_eval.py --update-readme` - BOQ parser against the hand-checked answers.
- `python evaluation/run_chat_eval.py` - chat sentences (needs keys; set PRIMARY=groq to use Groq first).
- `python evaluation/run_tender_eval.py` - tender questions on the full PDFs (set TENDER_DIR to the Drive folder).
- `python evaluation/run_urdu_eval.py` - Urdu translation checks and a sheet for a person to rate.

## Deploying
The app runs on Streamlit Community Cloud from this repository (branch `main`, file `app.py`, Python 3.11). Every push redeploys it. The Streamlit version is pinned in `requirements.txt`.

## Adding support for a new tender layout
1. Put a small excerpt of the BOQ pages in `tests/fixtures/` (no contact details) and add its expected rows to `evaluation/gold/`.
2. If a column has a new name, add it to `boq_columns` in `config/settings.yaml`.
3. Run the parser evaluation and look at the rows marked for review.

## When something breaks
- `ModuleNotFoundError` - the session was reset. Install the requirements again.
- "text not found" in a patch cell - the file differs from what was expected. Look at the file before changing anything.
- Old behaviour after a code change in Colab - Python still holds the old code in memory. Restart the session or run the code as a fresh program.
