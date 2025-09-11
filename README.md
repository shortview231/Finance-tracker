# Finance Tracker — Automated Data Pipeline

## At a Glance
- **Goal:** Transform messy personal finance data into a professional analytics system.  
- **Stack:** Google Sheets → Python (Pandas, API) → BigQuery (Cloud Warehouse) → Looker Studio (Dashboards).  
- **Features:** End-to-end ETL pipeline, automated data cleaning, cloud-based storage, real-time BI dashboards.  
- **Outputs:** Interactive Looker dashboards with KPIs, category analysis, and financial trends.  
- **Demo:** [Live Dashboard](https://lookerstudio.google.com/reporting/46d94a06-c659-4b94-893c-0161a8a5b752)  
- **Proof:** [Finance Tracker Proof Pack (PDF)](assets/finance_tracker_proof_pack.pdf)  

---

## Tech Stack
- **Python Libraries:** Pandas, NumPy, Google API Client, BigQuery Python SDK  
- **Data Storage:** Google Sheets, Google BigQuery  
- **Visualization:** Looker Studio  
- **Development Tools:** Git/GitHub, VS Code  

---

## 1. Input — Google Sheets Ledger
The system starts with a structured Google Sheet used as the raw ledger. Required columns:

- `date` — when the transaction occurred  
- `vendor` — payee or source  
- `amount` — positive = income, negative = expense  
- `category` — groceries, bills, fuel, etc.  
- `payment_method` — card, bank, cash, etc.  

**Rationale:** A clear input schema ensures automation works without manual cleanup.

---

## 2. Processing — Python ETL
Python scripts transform the raw sheet into structured, validated data.  

**Repo structure:**

finance-tracker/
│── tracker_api.py # Orchestration, API calls
│── clean.py # Normalization and parsing
│── schema.py # BigQuery table schema
│── utils/ # Helpers for validation, dates, logging


**Pipeline steps:**
1. **Ingest** transactions via the Google Sheets API.  
2. **Clean**: normalize dates, parse amounts, standardize categories.  
3. **Validate**: check required fields, flag errors, enforce schema.  
4. **Prepare**: output structured rows for loading into BigQuery.  

**Why this matters:** the ETL layer ensures every record is accurate, consistent, and analysis-ready.

---

## 3. Storage — Google BigQuery
Cleaned data is loaded into BigQuery, creating a scalable cloud warehouse.  

- **Centralized:** all financial history in one location.  
- **Structured:** explicit schema for transactions.  
- **Scalable:** supports years of financial records with query-level analytics.  

Data is appended automatically using the BigQuery Python client.

---

## 4. Visualization — Looker Studio Dashboards
Looker Studio connects directly to BigQuery for live analytics.  

Delivered dashboards include:  
- **KPI Gauges:** monthly income vs. expenses.  
- **Trends:** line charts showing income, expenses, and savings rate over time.  
- **Breakdowns:** category pie charts and tables for granular insight.  

![Dashboard Screenshot](assets/dashboard_screenshot.png)  

- [View Live Dashboard](https://lookerstudio.google.com/reporting/46d94a06-c659-4b94-893c-0161a8a5b752)  
- [Download Proof Pack (PDF)](assets/finance_tracker_proof_pack.pdf)  

---

## 5. Lessons Learned
- Start simple with clean headers; complexity comes later.  
- Always separate logic into files/modules to scale and maintain easily.  
- Cloud-first mindset: even personal projects benefit from warehouse + BI design.  
- Documentation matters: a project is only complete when its story is clear.  

---

## 6. Setup (Optional for Users)
1. Clone the repo.  
2. Create a Google Sheet with the headers listed above.  
3. Configure a BigQuery dataset and table (see `schema.py`).  
4. Add Google API credentials to your environment.  
5. Run the pipeline:  
   ```bash
   python tracker_api.py
Connect Looker Studio to BigQuery.

View dashboards.

7. Future Roadmap

This project is already fully functional, but I have plans to expand it further:

Backfill historical data: integrating past years of bank transactions for long-term analysis.

Automated ingestion: parsing emails and bank exports to remove all manual entry.

Forecasting models: projecting income, expenses, and savings to improve financial planning.

Tax preparation insights: generating categorized, year-end reports to simplify filing season.

Personal finance app vision: evolving into a fully automated, always-on personal banking assistant.

Conclusion

This project demonstrates how everyday financial tracking can be elevated into a full analytics pipeline. What begins as a simple Google Sheet evolves into a production-style ETL system with automated cleaning, cloud storage, and interactive BI dashboards.

Key takeaway: data engineering is about turning raw, chaotic inputs into clear, actionable insights — whether for a Fortune 500 company or personal finance.
   
