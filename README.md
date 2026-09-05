# Finance Tracker Data Pipeline

A portfolio project demonstrating how structured transaction data can be cleaned, validated, modeled, stored, and presented through an analytics workflow.

## At a glance

- **Stack:** Google Sheets, Python, Pandas, BigQuery, Looker Studio
- **Focus:** data cleaning, ETL, schema validation, warehouse loading, KPI reporting
- **Output:** analysis-ready transaction data and interactive business-intelligence views

This repository is intended as technical portfolio evidence. Any example or demonstration data should remain synthetic or appropriately sanitized.

## Pipeline

```text
structured ledger
  -> Python ingestion
  -> cleaning and normalization
  -> schema validation
  -> BigQuery storage
  -> Looker Studio reporting
```

## 1. Input layer

The pipeline starts from a structured ledger with fields such as:

- `date`
- `vendor`
- `amount`
- `category`
- `payment_method`

A defined input schema reduces downstream cleanup and makes validation rules explicit.

## 2. Python transformation layer

Python and Pandas handle the main transformation work:

1. ingest structured transaction rows
2. normalize dates and numeric values
3. standardize categories and text fields
4. validate required fields
5. flag malformed records
6. prepare clean rows for warehouse loading

Representative modules separate orchestration, cleaning, schema definition, and helper logic so the pipeline is easier to test and maintain.

## 3. BigQuery storage

Validated rows are loaded into BigQuery using an explicit table schema. This provides a central analytical layer that can support historical queries, aggregation, and dashboard reporting.

## 4. Reporting

Looker Studio connects to the analytical tables for views such as:

- income and expense KPIs
- category breakdowns
- monthly trends
- transaction-level tables
- savings and cash-flow summaries where supported by the data

## Engineering practices demonstrated

- explicit input schemas
- repeatable data cleaning
- separation of transformation logic from presentation
- validation before warehouse loading
- documented analytical assumptions
- cloud data-warehouse usage
- business-intelligence reporting
- maintainable project structure

## Skills demonstrated

- Python
- Pandas
- Google Sheets API workflows
- BigQuery
- SQL-oriented data modeling
- ETL and data cleaning
- Looker Studio
- KPI design
- technical documentation

## Data-safety boundary

This public repository should contain only sanitized or synthetic examples. Credentials, account identifiers, private financial records, personal transaction history, and production configuration do not belong in the public repository.

## Portfolio positioning

The project demonstrates a practical data-engineering pattern: take messy operational records, apply repeatable validation and transformation rules, store the result in an analytical system, and surface decision-ready reporting.