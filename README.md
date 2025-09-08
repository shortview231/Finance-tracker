# Finance-Tracker

A Python project that ingests a Google Sheets cashflow ledger, cleans and normalizes the data, syncs posted rows to Google Calendar, and generates financial charts. Built as a personal finance tool and portfolio project.

---

## ⚠️ Project Update: Evolving the Data Ecosystem

This project is being re-architected into a fully automated, cloud-based data pipeline. We are moving from a local CLI to a serverless layout using Google Cloud Functions, BigQuery, and Looker Studio to create an end to end data ecosystem.

This includes simplifying the Google Sheets ledger. The new, cleaner sheet will serve as a simple data input form. The full processing and analysis will happen in the cloud.

---

## Environment setup and troubleshooting log (Sept 7, 2025)

**Context:** We needed Python 3.11 primarily for `tomllib`. VS Code showed 3.11 selected, yet Pylance kept resolving libraries like it was on 3.10. `matplotlib` also raised import errors even after reinstall.

**Symptoms observed:**

* VS Code status bar indicated 3.11, but Pylance behaved as if 3.10.
* `import matplotlib` unresolved or ImportError in the editor.
* Clearing caches and reinstalling libraries did not help at first.

**What finally worked:**

1. Remove `.vscode/` and `.venv/` in the project root.
2. Create a fresh environment with the explicit 3.11 binary:

   ```bash
   /usr/bin/python3.11 -m venv .venv
   ./.venv/bin/python -m pip install --upgrade pip setuptools wheel
   ```
3. Reinstall project dependencies into that environment.
4. In VS Code run Python: Select Interpreter and choose `.venv/bin/python`.
5. Restart Pylance and reload the window.
6. Verify inside the VS Code terminal:

   ```bash
   which python
   python -V
   python -c "import matplotlib, sys; print(matplotlib.__version__, sys.executable)"
   ```

**Outcome:** Pylance now indexes 3.11 correctly. `matplotlib` imports cleanly.

**Takeaway:** It took persistence and plenty of trial and error. Two paid LLMs tried to guide the process, but stubborn resets and explicit interpreter selection are what fixed it.

---

## Demo dataset and proxy data

We now include a demo sheet as the primary example dataset for this repo. The code can also populate the sheet with proxy data. This lets you run the entire pipeline without connecting to live sources.

**Quick start with demo data:**

```bash
/usr/bin/python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python path/to/script_that_populates_demo.py   # creates and loads proxy data
python path/to/analysis_or_viz_script.py      # runs analysis and matplotlib viz
```

Notes:

* Proxy data is clearly labeled and safe to share.
* Swap to real data later by updating data paths or environment variables.

---

## Features (to date)

### ✅ Data Cleaning Pipeline

Implemented in `tracker/clean.py`:

* Column headers to `snake_case`.
* Text normalization to trimmed lowercased fields with `*_norm` columns.
* Date parsing from raw strings to `date_dt` in ISO format.
* Amount parsing from `$1,234.56` to `1234.56` with negatives like `(45.00)`.
* Type normalization to `type_norm` with `income` or `expense`.
* Validation of required columns, missing values, and duplicates.
* Category mapping to stable `category_norm` buckets.
* Payment method mapping to `payment_method_norm`.
* Signed amounts with `amount_signed` where income is positive and expense negative.
* Buckets for Needs, Wants, Savings, Taxes, Income.
* `[UNMAPPED]` report that surfaces stray values for review.

### ✅ CLI (`tracker_api.py`)

**clean**

* Preview cleaned ledger in the terminal.
* `--save --to-csv` saves to `charts/cleaned_preview.csv`.
* `(Optional)` `--to-sheet` planned to write to `Ledger_CLEAN` tab in Google Sheets.

**charts**
Generates baseline charts:

* Daily Net `daily_net.png`
* Running Balance `running_balance.png`
* Expenses by Category `expenses_pie.png`

Generates extra charts:

* Daily Net with 7 day MA `daily_net_ma.png`
* Running Balance Overlay Planned vs Posted `running_balance_overlay.png`
* Spending by Bucket `expenses_bucket.png`
* Monthly Totals `monthly_totals.png` and `monthly_totals.csv`
* Expenses by Payment Method `expenses_by_payment.png`

**sync-cal** (stub)

* Will push rows where `posted == TRUE` into Google Calendar. Income green, Expense red.
* Currently previews event payloads only.

**scenarios** (preview)

* Generates synthetic low, medium, and high demo ledgers.
* Produces demo charts into `charts/`.

---

## Project Checklist

### Setup and Infrastructure

* [x] Initialize repo and `.gitignore` for `credentials.json`, `token*.json`, `.venv/`, `charts/*.png`
* [x] Create `tracker/` package `clean.py`, `charts.py`, `io.py`, and more
* [x] CLI scaffold `tracker_api.py` with subcommands
* [x] Google API auth working with `credentials.json` and `token.json`
* [x] Config system `config.toml`
* [ ] Write clear `README.md` with setup and screenshots

### Data Cleaning (Milestone 1)

* [x] Column headers with `normalize_columns`
* [x] Text normalization with `lowercase_strings`
* [x] Date parsing with `coerce_date` to `date_dt`
* [x] Amount parsing with `coerce_amount` to `amount_num`
* [x] Type normalization with `normalize_type` to `type_norm`
* [x] Validation step for required columns, missing values, and duplicates
* [x] Category mapping to `category_norm`
* [x] Payment method mapping to `payment_method_norm`
* [x] Signed amounts to `amount_signed`
* [x] Bucket classification Needs, Wants, Savings, Taxes, Income
* [x] Safe persist target `clean --save --to-csv`
* [ ] Safe persist target `clean --save --to-sheet`

### Charts and Analysis (Milestone 2)

* [x] Daily net chart `daily_net.png`
* [x] Running balance chart `running_balance.png`
* [x] Daily net with 7 day moving average `daily_net_ma.png`
* [x] Running balance overlay Planned vs Posted `running_balance_overlay.png`
* [x] Expenses by category pie chart `expenses_pie.png`
* [x] Spending by bucket `expenses_bucket.png`
* [x] Monthly rollups `monthly_totals.png` and CSV export
* [x] Expense breakdown by payment method `expenses_by_payment.png`

### Calendar Sync (Milestone 3)

* [ ] Implement `sync-cal`
* [ ] Read ledger rows where `posted == TRUE`
* [ ] Push to Google Calendar as events. Income green. Expense red.
* [ ] Dry run mode vs write mode

### Scenarios and Demo Mode (Milestone 4)

* [x] Implement `scenarios` command to create baseline synthetic ledgers and charts
* [ ] Expand demo with low, medium, high CSVs
* [ ] Generate bucket and monthly charts in scenarios

### The Cloud Pipeline (Milestone 5)

**Phase 1: Cloud Project Setup**

* [ ] Create a new Google Cloud project
* [ ] Enable APIs for Sheets, BigQuery, Cloud Functions, Calendar, Gmail
* [ ] Create a dedicated service account for the pipeline

**Phase 2: The Data Warehouse**

* [ ] Create a BigQuery Dataset
* [ ] Create a BigQuery Table with a defined schema for the cleaned ledger

**Phase 3: The Cloud Function**

* [ ] Refactor core logic into a single deployable Python function
* [ ] Deploy the function to Google Cloud
* [ ] Set an automated trigger to run on a schedule

**Phase 4: The Final Automation**

* [ ] Write data to BigQuery instead of local CSV
* [ ] Add Calendar API logic to create bill events automatically
* [ ] Add Gmail API logic to send a daily financial summary email

**Recurring Bills (Optional Expansion)**

* [ ] Implement `[Recurring]` tab expansion into dated rows
* [ ] Merge with Ledger for planning view
* [ ] Add Planned vs Posted comparison line in charts
* [ ] Alert if 30 day projected balance is less than zero

**Polish and Portfolio Prep**

* [ ] Fill out README with setup instructions and screenshots
* [ ] Add safe sample data without PII
* [ ] Add MIT License
* [ ] Record a 2 minute demo script flow. Show charts. Run scenarios. Flip a rent row `posted = TRUE` and show the new calendar event.

---

## Appendix: Matplotlib and environment sanity checks

If you ever see unresolved import for matplotlib:

```bash
./.venv/bin/python -c "import matplotlib, sys; print('OK', matplotlib.__version__, sys.executable)"
```

If that prints OK and the path into `.venv`, reload the VS Code window and restart Pylance. If it fails, reinstall inside the active environment:

```bash
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install matplotlib
```

Everything above should keep the project stable on Python 3.11 going forward.
