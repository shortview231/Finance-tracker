# Finance Tracker (Sheets + Calendar + Charts)

A Python project that reads a Google Sheet as a **cashflow ledger**, cleans it with pandas, and (soon) generates charts and syncs paid items to Google Calendar.

## What it does today
- Authenticates to Google Sheets (read-only).
- Loads **Ledger** tab and normalizes column headers to `snake_case`.
- Creates cleaned, lowercased `*_norm` versions of key text columns (type, category, payment_method, description, name).
- Prints previews for quick verification.

## Roadmap (near-term)
- Parse dates and amounts; add `signed_amount`.
- Daily Summary (auto-roll current month).
- Monthly Summary / YTD rollups.
- Expenses view: Recurring (by due date) vs Variable.
- Charts (matplotlib PNGs to `charts/`) and/or live Sheets charts.
- Calendar sync for `posted == TRUE`.

---

## Repo Structure

`