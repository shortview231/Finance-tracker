# Finance-Tracker

A Python project that ingests a Google Sheets cashflow ledger, cleans and normalizes the data, syncs posted rows to Google Calendar, and generates financial charts.  
Built as a personal finance tool and portfolio project.

---

## 🚀 Features (to date)

### ✅ Data Cleaning Pipeline
Implemented in [`tracker/clean.py`](tracker/clean.py):
- **Column headers** → normalized to `snake_case`.
- **Text normalization** → trimmed + lowercased with `*_norm` columns.
- **Date parsing** → raw strings → `date_dt` (ISO format).
- **Amount parsing** → `$1,234.56` → `1234.56` (handles negatives like `(45.00)`).
- **Type normalization** → maps variants → `type_norm` (`income` / `expense`).
- **Validation** → checks required cols, prints missing values + duplicates.
- **Category mapping** → raw labels → stable `category_norm` buckets.
- **Payment method mapping** → card/cash/transfer, etc. → `payment_method_norm`.
- **Signed amounts** → `amount_signed` (+ income, – expense).
- **Buckets** → Needs / Wants / Savings / Taxes / Income.
- **[UNMAPPED] report** → surfaces any stray values for review.

### ✅ CLI (`tracker_api.py`)
- **`clean`**  
  - Preview cleaned ledger in the terminal.  
  - `--save --to-csv` → saves to `charts/cleaned_preview.csv`.  
  - (Optional) `--to-sheet` → planned: write to `Ledger_CLEAN` tab in Google Sheets.

## 📊 Charts (Generated)

- ![Daily Net](charts/daily_net.png)
- ![Running Balance](charts/running_balance.png)
- ![Expenses by Category](charts/expenses_pie.png)
- ![Spending by Bucket](charts/expenses_bucket.png)
- ![Monthly Totals](charts/monthly_totals.png)
- ![Expenses by Payment Method](charts/expenses_by_payment.png)

- **`sync-cal`** *(stub)*  
  - Will push rows where `posted == TRUE` into Google Calendar (Income = green, Expense = red).  
  - Currently previews event payloads.

- **`scenarios`** *(stub)*  
  - Will generate low/medium/high income demo ledgers and charts.

### ✅ Docs
- **Before Cleaning (PDF)** — raw CSV screenshots for portfolio/demo.  
  - [📄 View PDF](docs/csv_before_photos.pdf)

---

## 📊 Example Workflow

```bash
# Preview cleaning
python tracker_api.py clean

# Save cleaned data to CSV
python tracker_api.py clean --save --to-csv

# Generate charts from cleaned data
python tracker_api.py charts


## 📋 Project Checklist

### Setup / Infrastructure
- [x] Initialize repo + `.gitignore` (`credentials.json`, `token*.json`, `.venv/`, `charts/*.png`)
- [x] Create `tracker/` package (`clean.py`, `charts.py`, `io.py`, etc.)
- [x] CLI scaffold (`tracker_api.py` with subcommands)
- [x] Google API auth working (`credentials.json`, `token.json`)
- [x] Config system (`config.toml`)
- [ ] Write clear **README.md** with setup + screenshots (in progress)

---

### Data Cleaning (Milestone 1 ✅)
- [x] **Column headers** → `normalize_columns`
- [x] **Text normalization** → `lowercase_strings`
- [x] **Date parsing** → `coerce_date` → `date_dt`
- [x] **Amount parsing** → `coerce_amount` → `amount_num`
- [x] **Type normalization** → `normalize_type` → `type_norm`
- [x] **Validation step** (required cols, missing values, duplicates)
- [x] **Category mapping** → `category_norm`
- [x] **Payment method mapping** → `payment_method_norm`
- [x] **Signed amounts** → `amount_signed`
- [x] **Bucket** → Needs / Wants / Savings / Taxes / Income
- [x] **Safe persist target** → `clean --save --to-csv`
- [ ] Safe persist → `clean --save --to-sheet`

---

### Charts & Analysis (Milestone 2 🚧)
- [x] Daily net chart (`daily_net.png`)
- [x] Running balance chart (`running_balance.png`)
- [x] Expenses by category pie chart (`expenses_pie.png`)
- [ ] Expenses by bucket (Needs/Wants/etc.)
- [ ] Monthly rollups
- [ ] Planned vs Posted comparison
- [ ] Expense breakdown by payment method

---

### Calendar Sync (Milestone 3 🚧)
- [ ] Implement `sync-cal`
- [ ] Read ledger rows where `posted == TRUE`
- [ ] Push to Google Calendar as events (Income = green, Expense = red)
- [ ] Dry-run mode vs write mode

---

### Scenarios / Demo Mode (Milestone 4 🚧)
- [ ] Implement `scenarios`
- [ ] Auto-generate 3 demo ledgers: low, medium, high income
- [ ] Save cleaned CSVs
- [ ] Generate charts for each

---

### Recurring Bills (Optional Expansion)
- [ ] Implement `[Recurring]` tab expansion into dated rows
- [ ] Merge with Ledger for planning view
- [ ] Add Planned vs Posted comparison line in charts
- [ ] Alert if 30-day projected balance < 0

---

### Polish & Portfolio Prep
- [ ] Fill out **README.md** with setup instructions + screenshots
- [ ] Add safe sample data (no PII)
- [ ] Add MIT LICENSE
- [ ] Record 2-minute demo script flow:
  - Show charts
  - Run scenarios
  - Flip a rent row `posted = TRUE` → show new calendar event
