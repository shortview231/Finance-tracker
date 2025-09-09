Finance-Tracker

A cloud-first personal finance pipeline built as a portfolio project and professional case study.

🚀 Overview

Finance-Tracker is a Python project that:

Ingests a Google Sheets ledger (with demo data included).

Cleans and normalizes the data with a robust pipeline (tracker/clean.py).

Uploads the cleaned data to BigQuery for warehouse-grade analysis.

Generates charts (matplotlib) for daily, monthly, and categorical spending.

(Planned) Syncs transactions into Google Calendar and sends summary emails.

What began as a local CLI tool is now evolving into a serverless, automated, cloud-native data ecosystem powered by Google Cloud Functions, BigQuery, and Looker Studio.

🧩 Architecture
flowchart TD
  A[Google Sheets Ledger / Demo Data] --> B[Python ETL: tracker_api.py]
  B --> C[Data Cleaning: tracker/clean.py]
  C --> D[BigQuery Warehouse]
  D --> E[Looker Studio Dashboards]
  C --> F[Matplotlib Charts: charts/*.png]
  C --> G[Google Calendar Sync (planned)]
  C --> H[Gmail Daily Summary (planned)]

✨ Features
🔹 Data Cleaning (tracker/clean.py)

Standardizes headers → snake_case.

Normalizes text with typo fixes (*_norm fields).

Parses dates and amounts (robust handling of negatives & bad formats).

Maps transaction types → income / expense.

Canonicalizes categories and payment methods.

Adds signed amounts and buckets (Needs / Wants / Savings / Taxes).

Surfaces unmapped values for debugging.

🔹 CLI (tracker_api.py)

scenarios: generates low/medium/high demo ledgers + charts.

clean: runs the full pipeline, validates, and uploads to BigQuery.

--save --to-csv → saves to charts/cleaned_preview.csv.

--to-sheet (planned) → saves back to Google Sheets.

charts: daily net, running balance, expenses by category/bucket/payment method.

sync-cal (planned): push posted transactions into Google Calendar.

🔹 Cloud Pipeline

BigQuery dataset: finance_data.

Table: cleaned_transactions.

Schema auto-enforced and column names sanitized for BigQuery compatibility.

Ready for Looker Studio dashboards.

⚠️ Debugging Lessons Learned

This repo documents real troubleshooting (not just polished code). Some highlights:

Interpreter mismatch (Python 3.10 vs 3.11 in VS Code).

matplotlib import hell fixed by nuking .venv and .vscode.

TOML config collisions (duplicate [google] blocks).

BigQuery upload failures (illegal field names like progress_to_$2400_cap). Fixed via a sanitize_column_names_for_bq helper.

Service account key issues (empty JSON, wrong folder name). Solved by consistent cloud_key/ structure and .gitignore.

👉 These battle logs are included because debugging is part of engineering.

📂 Repo Structure
Finance-tracker/
├── charts/                  # Generated charts & CSVs (ignored by git)
├── cloud_key/               # Service account keys (ignored by git)
├── tracker/
│   ├── clean.py             # Core cleaning pipeline
│   ├── charts.py            # Chart generation
│   ├── io.py                # Google Sheets I/O
│   ├── bq.py                # BigQuery upload logic
│   ├── mappings.py          # Header/category/payment canonicalization
│   └── schema.py            # Schema enforcement
├── tracker_api.py           # CLI entrypoint
├── config.toml              # Project config (safe version)
└── requirements.txt

🔧 Setup
# Clone and enter
git clone https://github.com/shortview231/Finance-tracker.git
cd Finance-tracker

# Create virtual environment
/usr/bin/python3.11 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run demo scenarios
python tracker_api.py scenarios

# Run cleaning pipeline (outputs to BigQuery + CSV)
python tracker_api.py clean --save --to-csv

🗓 Roadmap

 Local cleaning + charting.

 BigQuery integration.

 Looker Studio dashboards.

 Google Calendar sync.

 Gmail daily/weekly financial summary.

 Recurring bills modeling.

 Full serverless deployment (Cloud Functions).