# Bidding Helper AI

[![Tests](https://github.com/YOUR-USERNAME/bidding-helper-ai/actions/workflows/tests.yml/badge.svg)](https://github.com/YOUR-USERNAME/bidding-helper-ai/actions/workflows/tests.yml)

A free chatbot for contractors. Upload a tender PDF (EPADS format) and ask it to:

- build the **BOQ as an Excel file**,
- list the tender **requirements**, **forms**, dates and money figures,
- edit rates on rows you choose (with a preview first),
- translate item descriptions into **Urdu**.

Uncertain items are shown under **needs review** instead of being guessed. Always
check results against the PDF before bidding.

**Status:** under construction. See [docs/ROADMAP.md](docs/ROADMAP.md).

## Run the tests in Google Colab

Open `notebooks/colab_run.ipynb` in Colab and run the cells from top to bottom.

## Bring your own API key

Each person uses their own free LLM keys (Gemini, Groq). Keys stay in the browser
session only and are never saved or committed.
