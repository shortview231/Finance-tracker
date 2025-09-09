# tracker_api.py
# CLI for Finance-tracker: clean data, make charts, preview sync-cal & scenarios

import argparse
from pathlib import Path
from typing import Tuple, List, Dict, Any

import pandas as pd
import matplotlib.pyplot as plt

from tracker.clean import clean_ledger, validate_ledger, clean_doordash_data
from tracker.io import read_sheets_to_dfs, write_df_to_sheet
from tracker.bq import upload_to_bigquery


# Optional extras from tracker.charts; safe if not present
try:
    from tracker.charts import extra_charts, _month_frame  # optional helpers
except Exception:
    extra_charts = None
    _month_frame = None

# Demo redaction toggle for public scenarios (weed -> medicine)
DEMO_REDACT_CATEGORIES = True

# Paths
CHARTS_DIR = Path("charts")
CHARTS_DIR.mkdir(parents=True, exist_ok=True)

RUNNING_BALANCE_PNG = CHARTS_DIR / "running_balance.png"
DAILY_NET_PNG = CHARTS_DIR / "daily_net.png"
EXPENSES_PIE_PNG = CHARTS_DIR / "expenses_pie.png"
CLEANED_PREVIEW_CSV = CHARTS_DIR / "cleaned_preview.csv"


# --------------------------
# Helpers
# --------------------------
def _merge_dfs(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Merges all DataFrames into a single, comprehensive DataFrame for analysis.
    """
    df_ledger = dfs.get("Ledger", pd.DataFrame())
    df_expenses = dfs.get("Expenses", pd.DataFrame())
    df_doordash = dfs.get("DoorDash", pd.DataFrame())
    df_goals = dfs.get("Goals", pd.DataFrame())
    
    # 1. Clean the DoorDash data
    if not df_doordash.empty and not df_goals.empty:
        df_doordash = clean_doordash_data(df_doordash, df_goals)
    
    # 2. Add a 'type' column to the DoorDash data
    if not df_doordash.empty:
        df_doordash['type'] = 'income'

    # 3. Merge the Ledger and DoorDash data
    df_merged = pd.concat([df_ledger, df_doordash], ignore_index=True)
    
    return df_merged


def _load_clean_df(prefer_csv: bool = True) -> pd.DataFrame:
    """
    Load a cleaned dataframe:
      - if charts/cleaned_preview.csv exists and prefer_csv=True, load it;
      - else read raw data from Sheets and run clean_ledger.
    Ensures: date_dt, type_norm, amount_num, amount_signed (and category_norm if available).
    """
    if prefer_csv and CLEANED_PREVIEW_CSV.exists():
        print(f"ℹ️ Using cleaned preview CSV → {CLEANED_PREVIEW_CSV}")
        df = pd.read_csv(CLEANED_PREVIEW_CSV)
        # best-effort ensure dtypes
        if "date_dt" in df.columns:
            df["date_dt"] = pd.to_datetime(df["date_dt"], errors="coerce")
        for c in ("amount_num", "amount_signed"):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        # normalize posted column shape if present in CSV
        if "posted" in df.columns:
            # coerce posted to boolean-ish values
            s = df["posted"].astype(str).str.strip().str.lower()
            df["posted"] = s.isin({"true", "t", "yes", "y", "1", "paid"})
        return df
    
    # Read all sheets into a dictionary of DataFrames
    print("ℹ️ No cleaned_preview.csv (or bypassed) — reading all ledgers from Sheets and cleaning.")
    raw_dfs = read_sheets_to_dfs(
        tab_names=["Ledger", "Expenses", "DoorDash", "Goals"]
    )
    
    merged_df = _merge_dfs(raw_dfs)
    
    df = clean_ledger(merged_df)
    
    return df


def _save_clean_preview_csv(df: pd.DataFrame, path: Path = CLEANED_PREVIEW_CSV):
    df_out = df.copy()
    # Save friendly string dates
    if "date_dt" in df_out.columns:
        df_out["date_dt"] = pd.to_datetime(df_out["date_dt"], errors="coerce").dt.strftime("%Y-%m-%d")
    df_out.to_csv(path, index=False)
    print(f"✅ Saved cleaned preview to {path}")


def _require_columns(df: pd.DataFrame, cols: Tuple[str, ...]):
    missing = set(cols) - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def _posted_mask(df: pd.DataFrame) -> pd.Series:
    """
    Unified 'posted' mask:
      - prefer new unified 'posted' column (bool)
      - else fall back to legacy 'posted_bool'
      - else treat everything as posted (all True)
    """
    if "posted" in df.columns:
        return df["posted"].fillna(True) == True  # noqa: E712
    if "posted_bool" in df.columns:
        return df["posted_bool"].fillna(True) == True  # noqa: E712
    # No flag columns at all: assume posted
    return pd.Series(True, index=df.index)


# --------------------------
# DEMO DATA GENERATION HELPERS
# --------------------------
# Realism helpers
from datetime import date, timedelta
import numpy as np


def _demo_rng():
    # Stable randomness per run without affecting global numpy state
    return np.random.default_rng(20250908)


def _closest_friday_if_weekend(d: date) -> date:
    # Simple weekend rule; holiday list can be added later
    if d.weekday() in (5, 6):
        while d.weekday() != 4:
            d -= timedelta(days=1)
    return d


def _recurring_bills(year: int, month: int) -> List[Dict[str, Any]]:
    # Fixed bills with categories that already exist in your mappings
    bills = [
        {"day": 1,  "desc": "Rent",       "category": "rent",  "amount": -850, "source": "landlord"},
        {"day": 12, "desc": "Utilities",  "category": "spire", "amount": -120, "source": "spire"},
        {"day": 15, "desc": "Phone Bill", "category": "phone", "amount": -75,  "source": "carrier"},
        {"day": 18, "desc": "Streaming",  "category": "misc",  "amount": -16,  "source": "netflix"},
    ]
    rows: List[Dict[str, Any]] = []
    for b in bills:
        try:
            d = date(year, month, b["day"])
        except ValueError:
            continue
        rows.append({
            "date": d.isoformat(),
            "type": "expense",
            "category": b["category"],
            "description": b["desc"],
            "amount": float(b["amount"]),
            "source": b["source"],
            "posted": "true",
        })
    return rows


def _disability_income_row(year: int, month: int, amount: float = 1200.0) -> Dict[str, Any]:
    base = date(year, month, 3)
    pay_day = _closest_friday_if_weekend(base)
    return {
        "date": pay_day.isoformat(),
        "type": "income",
        "category": "disability",
        "description": "Disability deposit",
        "amount": float(amount),
        "source": "ssa",
        "posted": "true",
    }


def _random_day_transactions(year: int, month: int, d: int, income_level: str, rng: np.random.Generator) -> List[Dict[str, Any]]:
    """Produce 0–6 transactions for a single day with varied amounts/categories."""
    try:
        dt = date(year, month, d)
    except ValueError:
        return []

    # Poisson-like draw for count, then clamp
    n = int(rng.poisson(2))
    n = max(0, min(n, 6))

    # income baselines by level
    income_base = {"low": 45, "medium": 110, "high": 200}[income_level]
    exp_mu = {"low": 18, "medium": 28, "high": 42}[income_level]  # typical expense

    cats_expense = [
        ("groceries", 0.25, ["Groceries", "Food run", "Market haul"], ["debit card", "discover", "visa"]),
        ("gas",       0.20, ["Gas", "Fuel"],                            ["debit card", "discover"]),
        ("dining",    0.15, ["Coffee", "Snacks", "Lunch out"],          ["debit card", "visa"]),
        ("medicine",  0.05, ["Pharmacy"],                                 ["debit card"]),  # demo safe
        ("misc",      0.35, ["Supplies", "Errand", "Misc"],             ["debit card", "cash"]),
    ]

    rows: List[Dict[str, Any]] = []
    for _ in range(n):
        # mix of income and expenses
        is_income = rng.random() < 0.25  # 25 percent chance income-like
        if is_income:
            # noisy gig payout
            amt = income_base + rng.normal(0, income_base * 0.25)
            amt = round(max(15, amt), 2)
            rows.append({
                "date": dt.isoformat(),
                "type": "income",
                "category": "doordash",
                "description": "Gig payout",
                "amount": float(amt),
                "source": "doordash",
                "posted": "true",
            })
        else:
            # choose an expense category by weight
            p = rng.random()
            cum = 0.0
            chosen = cats_expense[-1]
            for c in cats_expense:
                cum += c[1]
                if p <= cum:
                    chosen = c
                    break
            cat, _, descs, sources = chosen
            # lognormal-ish positive then negated
            amt = float(max(5, rng.lognormal(mean=float(np.log(exp_mu)), sigma=0.5)))
            amt = round(-amt, 2)
            rows.append({
                "date": dt.isoformat(),
                "type": "expense",
                "category": cat,
                "description": rng.choice(descs),
                "amount": amt,
                "source": rng.choice(sources),
                "posted": "true",
            })
    return rows


def _redact_demo_categories(df: pd.DataFrame) -> pd.DataFrame:
    """Demo-only category redaction: show 'weed' as 'medicine' in demos."""
    if "category" in df.columns:
        out = df.copy()
        out["category"] = out["category"].replace({"weed": "medicine"})
        return out
    return df


def _apply_demo_redaction_if_enabled(df: pd.DataFrame) -> pd.DataFrame:
    try:
        if DEMO_REDACT_CATEGORIES:
            return _redact_demo_categories(df)
    except NameError:
        pass
    return df


def _generate_realistic_ledger(month_str: str, income_level: str) -> pd.DataFrame:
    """Central generator used by scenarios and demo data."""
    rng = _demo_rng()
    year, m = map(int, month_str.split("-"))

    rows: List[Dict[str, Any]] = []
    # recurring bills + disability income
    rows.extend(_recurring_bills(year, m))
    rows.append(_disability_income_row(year, m, amount=1200.0))

    # per-day random transactions for each day that exists
    for day in range(1, 32):
        rows.extend(_random_day_transactions(year, m, day, income_level, rng))

    df = pd.DataFrame(rows)

    # ensure required columns exist even if some lists empty
    for c in ["date", "type", "category", "amount", "source", "posted", "description"]:
        if c not in df.columns:
            df[c] = "" if c != "amount" else 0.0

    # demo-only redaction
    df = _apply_demo_redaction_if_enabled(df)

    return clean_ledger(df)


def _generate_demo_data(start_date: str, income_level: str) -> Dict[str, pd.DataFrame]:
    """
    Generates a full set of synthetic data for all sheets.
    Returns a dictionary of DataFrames.
    """
    from datetime import timedelta

    # Ledger: use realistic generator on the month of start_date
    month_str = pd.to_datetime(start_date).strftime("%Y-%m")
    ledger_df = _generate_realistic_ledger(month_str, income_level)

    # Expenses table (kept small and static)
    expenses_data = pd.DataFrame({
        "expense_name": ["Rent", "Phone Bill", "Netflix"],
        "amount": [850.00, 75.00, 15.49],
        "due_date": [1, 15, 18],
        "status": ["Due", "Due", "Due"],
    })

    # DoorDash raw orders (optional realism; safe to leave as-is)
    orders_per_day_mean = 5
    order_amount_mean = 8
    order_amount_std = 3

    orders = []
    current_date = pd.to_datetime(start_date)
    for i in range(30):  # 30 days
        num_orders = max(0, int(np.random.normal(orders_per_day_mean, 2)))
        for j in range(num_orders):
            order_amount = max(5, np.random.normal(order_amount_mean, order_amount_std))
            orders.append({
                "Date": (current_date + timedelta(days=i)).strftime("%Y-%m-%d"),
                "Order ID": f"DD-{i}-{j}",
                "Amount": round(float(order_amount), 2),
            })
    doordash_data = pd.DataFrame(orders)

    # Goals
    goals_data = pd.DataFrame({
        "metric": ["DoorDash Income Cap", "Monthly Savings Goal"],
        "value": [600, 200],
    })

    return {
        "Ledger": ledger_df,
        "Expenses": expenses_data,
        "DoorDash": doordash_data,
        "Goals": goals_data,
    }

# --------------------------
# CLEAN command
# --------------------------
def cmd_clean(
    preview: bool = True,
    save: bool = False,
    save_to_csv: bool = True,
    csv_path: str = str(CLEANED_PREVIEW_CSV),
    sheet_tab: str = "Ledger_CLEAN",
):
    """
    Run the full cleaning pipeline and preview results.
    Use --save to persist to CSV or to a Google Sheet tab.
    Auto-fallback: if the 'Ledger' tab is empty/missing, use a demo ledger tab.
    """
    # 1) Try the real tabs first
    dfs = read_sheets_to_dfs(tab_names=["Ledger", "Expenses", "DoorDash", "Goals"])

    ledger_df = dfs.get("Ledger", pd.DataFrame())
    if ledger_df is None or ledger_df.empty:
        print("ℹ️ 'Ledger' tab appears empty or missing — searching demo tabs…")

        # Try demo tabs in a sensible order
        demo_tabs = ["Demo_Ledger_medium", "Demo_Ledger_high", "Demo_Ledger_low"]
        demo_dfs = read_sheets_to_dfs(tab_names=demo_tabs)

        chosen_demo = None
        for tab in demo_tabs:
            df_demo = demo_dfs.get(tab, pd.DataFrame())
            if df_demo is not None and not df_demo.empty:
                chosen_demo = tab
                ledger_df = df_demo.copy()
                break

        if chosen_demo:
            print(f"✅ Using demo ledger: {chosen_demo}")
            dfs["Ledger"] = ledger_df
        else:
            print("⚠️ No demo tabs found with data. Aborting clean.")
            return

    # 2) Merge all frames (Ledger + DoorDash aggregation + etc.)
    merged_df = _merge_dfs(dfs)

    # 3) Clean
    dfc = clean_ledger(merged_df)

    # 3b) BigQuery-safe column names (fixes invalid names like 'progress_to_$2400_cap')
    try:
        from tracker.clean import sanitize_column_names_for_bq
        dfc = sanitize_column_names_for_bq(dfc)
    except Exception as e:
        print(f"ℹ️ Skipping column-name sanitization (not critical): {e}")

    # 4) Upload cleaned data to BigQuery
    try:
        from tracker.bq import upload_to_bigquery
        print("⏫ Uploading DataFrame to BigQuery …")
        upload_to_bigquery(dfc)
    except Exception as e:
        print(f"⚠️ BigQuery upload failed: {e}")

    # 5) Validation echo (on cleaned frame for a quick sanity view)
    try:
        validate_ledger(dfc)
    except Exception as e:
        print(f"⚠️ Validation check raised: {e}")

    # 6) PREVIEW BLOCKS
    print("\n=== HEAD (first 8 rows) ===")
    print(dfc.head(8))

    # Amounts
    cols_to_show_amt = [c for c in ["amount", "amount_num", "amount_signed"] if c in dfc.columns]
    if cols_to_show_amt:
        print("\n=== Amount Columns Preview ===")
        print(dfc[cols_to_show_amt].head(10))

    # Types
    cols_to_show_type = [c for c in ["type", "type_norm"] if c in dfc.columns]
    if cols_to_show_type:
        print("\n=== Type Columns Preview ===")
        print(dfc[cols_to_show_type].head(10))

    # Dates
    cols_to_show_date = [c for c in ["date", "date_dt"] if c in dfc.columns]
    if cols_to_show_date:
        print("\n=== Date Columns Preview ===")
        tmp = dfc[cols_to_show_date].copy()
        if "date_dt" in tmp.columns:
            tmp["date_dt"] = pd.to_datetime(tmp["date_dt"], errors="coerce").dt.strftime("%Y-%m-%d")
        print(tmp.head(10))
        if "date_dt" in dfc.columns:
            bad_dates = dfc[dfc["date_dt"].isna()]
            if not bad_dates.empty:
                print("\n=== Bad Dates (failed parse) ===")
                print(bad_dates[["date"]].head(20))

    # Posted (supports either or both columns)
    posted_cols = [c for c in ["posted", "posted_bool"] if c in dfc.columns]
    if posted_cols:
        print("\n=== Posted Preview ===")
        print(dfc[posted_cols].head(10))

    # Category
    cat_cols = [c for c in ["category", "category_norm"] if c in dfc.columns]
    if cat_cols:
        print("\n=== Category Preview ===")
        print(dfc[cat_cols].head(10))

    # 7) Persist if asked
    if save:
        if save_to_csv:
            _save_clean_preview_csv(dfc, Path(csv_path))
        else:
            try:
                from tracker.io import write_df_to_sheet
                df_sheet = dfc.copy()
                if "date_dt" in df_sheet.columns:
                    df_sheet["date_dt"] = pd.to_datetime(df_sheet["date_dt"], errors="coerce").dt.strftime("%Y-%m-%d")
                write_df_to_sheet(df_sheet, tab_name=sheet_tab)
                print(f"✅ Wrote cleaned preview to Sheet tab: {sheet_tab}")
            except ImportError:
                print("⚠️ write_df_to_sheet not found in tracker.io — CSV fallback recommended.")

# --------------------------
# CHARTS helpers
# --------------------------

def _daily_frames_from_clean(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Build daily net and running balance from cleaned columns.
    Requires: date_dt (datetime), amount_signed (float)
    """
    _require_columns(df, ("date_dt", "amount_signed"))

    wk = df.dropna(subset=["date_dt", "amount_signed"]).copy()
    wk["date"] = pd.to_datetime(wk["date_dt"], errors="coerce").dt.date

    # daily net = sum of signed amounts per day
    daily = wk.groupby("date", dropna=True)["amount_signed"].sum().rename("net").reset_index()

    # running balance (cumulative sum in chronological order)
    daily_sorted = daily.sort_values("date").reset_index(drop=True)
    daily_sorted["running_balance"] = daily_sorted["net"].cumsum()

    return daily_sorted[["date", "net"]], daily_sorted[["date", "running_balance"]]


def _plot_line(x, y, title: str, ylabel: str, outfile: Path, preview: bool = False):
    plt.figure()
    plt.plot(x, y)
    plt.title(title)
    plt.xlabel("Date")
    plt.ylabel(ylabel)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(outfile, dpi=160)
    if preview:
        plt.show()
    plt.close()
    print(f"✅ Saved {outfile}")


def _plot_pie(series: pd.Series, title: str, outfile: Path, preview: bool = False):
    plt.figure()
    series.plot(kind="pie", autopct="%1.0f%%")
    plt.ylabel("")
    plt.title(title)
    plt.tight_layout()
    plt.savefig(outfile, dpi=160)
    if preview:
        plt.show()
    plt.close()
    print(f"✅ Saved {outfile}")


def _plot_two_lines(x, y1, y2, label1: str, label2: str, title: str, ylabel: str, outfile: Path, preview: bool = False):
    plt.figure()
    plt.plot(x, y1, label=label1)
    plt.plot(x, y2, label=label2)
    plt.title(title)
    plt.xlabel("Date")
    plt.ylabel(ylabel)
    plt.xticks(rotation=45, ha="right")
    plt.legend()
    plt.tight_layout()
    plt.savefig(outfile, dpi=160)
    if preview:
        plt.show()
    plt.close()
    print(f"✅ Saved {outfile}")


def _daily_net_with_ma(df: pd.DataFrame, window: int = 7) -> pd.DataFrame:
    """
    Return a frame with columns: date, net, ma (moving average of net).
    Requires: date_dt, amount_signed.
    """
    need = {"date_dt", "amount_signed"}
    if not need.issubset(df.columns):
        raise ValueError("Missing required columns for daily net MA.")
    wk = df.dropna(subset=["date_dt", "amount_signed"]).copy()
    wk["date"] = pd.to_datetime(wk["date_dt"], errors="coerce").dt.date
    daily = wk.groupby("date")["amount_signed"].sum().rename("net").reset_index().sort_values("date")
    daily["ma"] = daily["net"].rolling(window=window, min_periods=1).mean()
    return daily


def _running_balance_overlay(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build a DataFrame with date, posted_running_balance, planned_running_balance.
    Requires: date_dt, amount_signed. Uses unified posted mask (prefers 'posted', falls back to 'posted_bool').
    """
    need = {"date_dt", "amount_signed"}
    if not need.issubset(df.columns):
        raise ValueError("Missing required cleaned columns for overlay.")

    wk = df.dropna(subset=["date_dt", "amount_signed"]).copy()
    wk["date"] = pd.to_datetime(wk["date_dt"], errors="coerce").dt.date

    # Planned includes everything
    planned = wk.groupby("date")["amount_signed"].sum().rename("planned_net").reset_index()
    planned = planned.sort_values("date")
    planned["planned_running_balance"] = planned["planned_net"].cumsum()

    # Posted only (unified)
    mask_posted = _posted_mask(wk)
    posted = wk[mask_posted].copy()
    if not posted.empty:
        posted = posted.groupby("date")["amount_signed"].sum().rename("posted_net").reset_index()
        posted = posted.sort_values("date")
        posted["posted_running_balance"] = posted["posted_net"].cumsum()
    else:
        posted = pd.DataFrame(columns=["date", "posted_running_balance"])

    # Merge & forward-fill posted line
    out = pd.merge(
        planned[["date", "planned_running_balance"]],
        posted[["date", "posted_running_balance"]],
        on="date", how="left"
    ).sort_values("date")
    out["posted_running_balance"] = out["posted_running_balance"].ffill()
    return out


# --------------------------
# CHARTS command
# --------------------------

def cmd_charts(preview: bool = False):
    df = _load_clean_df(prefer_csv=True)

    # Daily + Running Balance from signed amounts
    daily, run = _daily_frames_from_clean(df)
    _plot_line(
        daily["date"], daily["net"],
        "Daily Net", "Net ($)",
        DAILY_NET_PNG,
        preview=preview,
    )
    _plot_line(
        run["date"], run["running_balance"],
        "Running Balance", "Balance ($)",
        RUNNING_BALANCE_PNG,
        preview=preview,
    )

    # Daily Net with 7-day moving average (extra)
    try:
        d_ma = _daily_net_with_ma(df, window=7)
        outpath = CHARTS_DIR / "daily_net_ma.png"
        plt.figure()
        plt.plot(d_ma["date"], d_ma["net"], label="Daily Net")
        plt.plot(d_ma["date"], d_ma["ma"], label="7d MA")
        plt.title("Daily Net with 7-day MA")
        plt.xlabel("Date")
        plt.ylabel("Net ($)")
        plt.xticks(rotation=45, ha="right")
        plt.legend()
        plt.tight_layout()
        plt.savefig(outpath, dpi=160)
        if preview:
            plt.show()
        plt.close()
        print(f"✅ Saved {outpath}")
    except Exception as e:
        print(f"ℹ️ Skipping daily MA chart: {e}")

    # Expenses pie: prefer category_norm; fallback to category
    cat_col = "category_norm" if "category_norm" in df.columns else ("category" if "category" in df.columns else None)
    if cat_col is None:
        print("ℹ️ No category/category_norm column found; skipping expenses pie.")
    else:
        if "amount_signed" in df.columns:
            exp = df[df["amount_signed"] < 0].copy()
            if exp.empty:
                print("ℹ️ No expense rows found; skipping expenses pie.")
            else:
                exp["abs_amount"] = exp["amount_signed"].abs()
                by_cat = exp.groupby(cat_col, dropna=True)["abs_amount"].sum().sort_values(ascending=False)
                if not by_cat.empty:
                    pie_data = by_cat if len(by_cat) <= 8 else pd.concat(
                        [by_cat.head(8), pd.Series({"Other": by_cat.iloc[8:].sum()})]
                    )
                    _plot_pie(pie_data, "Expenses by Category", EXPENSES_PIE_PNG, preview=preview)
        else:
            # Very old frames fallback
            exp = df[df["type"].astype("string").str.lower().str.strip() == "expense"].copy()
            if not exp.empty:
                exp["abs_amount"] = pd.to_numeric(df["amount"], errors="coerce").abs()
                by_cat = exp.groupby(cat_col, dropna=True)["abs_amount"].sum().sort_values(ascending=False)
                if not by_cat.empty:
                    pie_data = by_cat if len(by_cat) <= 8 else pd.concat(
                        [by_cat.head(8), pd.Series({"Other": by_cat.iloc[8:].sum()})]
                    )
                    _plot_pie(pie_data, "Expenses by Category", EXPENSES_PIE_PNG, preview=preview)

    # Running balance overlay: planned vs posted (extra)
    try:
        ov = _running_balance_overlay(df)
        if not ov.empty:
            _plot_two_lines(
                ov["date"],
                ov["posted_running_balance"], ov["planned_running_balance"],
                "Posted", "Planned",
                "Running Balance — Planned vs Posted",
                "Balance ($)",
                CHARTS_DIR / "running_balance_overlay.png",
                preview=preview,
            )
        else:
            print("ℹ️ Overlay frame empty; skipping running_balance_overlay.png")
    except Exception as e:
        print(f"ℹ️ Skipping overlay chart: {e}")

    # Optional extras from tracker.charts (if present)
    try:
        if callable(extra_charts):
            extra_charts(df, CHARTS_DIR)
        if callable(_month_frame):
            mf = _month_frame(df)
            if not mf.empty:
                outcsv = CHARTS_DIR / "monthly_totals.csv"
                mf.to_csv(outcsv, index=False)
                print(f"✅ Saved {outcsv}")
    except Exception as e:
        print(f"ℹ️ Skipping optional extras: {e}")


# --------------------------
# SYNC-CAL command (previewable)
# --------------------------

def _preview_calendar_payloads(df: pd.DataFrame, max_rows: int = 10) -> List[Dict[str, Any]]:
    """
    Build preview of calendar event titles from cleaned rows with posted == True (fallback to posted_bool).
    """
    mask = _posted_mask(df)
    rows = df[mask & df["date_dt"].notna()].copy()
    if rows.empty:
        print("ℹ️ No posted rows to sync.")
        return []

    def title_for(r):
        t = str(r.get("type_norm", "")).title() or "Txn"
        # prefer normalized name/description when available
        src = r.get("name_norm") or r.get("source_norm") or r.get("description_norm") or r.get("source") or r.get("description") or ""
        amt = r.get("amount_num", r.get("amount_signed", 0.0))
        try:
            amt = float(amt)
        except Exception:
            amt = 0.0
        if t.lower() == "expense" and amt > 0:
            amt = -amt
        return f"{t} • {src} (${abs(amt):,.2f})".strip()

    rows = rows.sort_values("date_dt")
    previews: List[Dict[str, Any]] = []
    for _, r in rows.head(max_rows).iterrows():
        previews.append({
            "date": pd.to_datetime(r["date_dt"]).date().isoformat(),
            "title": title_for(r),
            "category": r.get("category_norm", r.get("category", "")),
            "payment_method": r.get("payment_method_norm", r.get("payment_method", "")),
        })

    print("\n=== Calendar Sync Preview (first up to 10) ===")
    for p in previews:
        print(f"{p['date']}  —  {p['title']}  [{p['category']}]  ({p['payment_method']})")

    more = max(0, len(rows) - min(max_rows, len(rows)))
    if more:
        print(f"… and {more} more posted rows ready.")

    return previews


def cmd_sync_cal(dry_run: bool = True):
    """
    Preview (or later: write) Google Calendar events for posted rows.
    Currently: preview only.
    """
    df = _load_clean_df(prefer_csv=True)
    previews = _preview_calendar_payloads(df, max_rows=10)

    if not dry_run and previews:
        print("⚠️ Write mode not implemented yet — this is a preview-only stub.")
    elif not previews:
        print("ℹ️ Nothing to sync.")


# --------------------------
# SCENARIOS command (previewable)
# --------------------------

def _synthesize_demo_ledger(month: str, income_level: str) -> pd.DataFrame:
    """
    Create a realistic synthetic ledger for demo charts.
    month: 'YYYY-MM' style
    income_level: 'low' | 'medium' | 'high'
    """
    return _generate_realistic_ledger(month, income_level)


def cmd_scenarios():
    print("📊 Generating demo scenarios (low/medium/high)…")
    for lvl in ("low", "medium", "high"):
        df_demo = _synthesize_demo_ledger("2025-08", lvl)
        
        # Write the generated DataFrame to a new tab in the Google Sheet
        print(f"Writing demo data for '{lvl}' scenario to Google Sheets...")
        write_df_to_sheet(df_demo, tab_name=f"Demo_Ledger_{lvl}")

        daily, run = _daily_frames_from_clean(df_demo)
        _plot_line(daily["date"], daily["net"], f"Daily Net — {lvl.title()}", "Net ($)", CHARTS_DIR / f"daily_net_{lvl}.png")
        _plot_line(run["date"], run["running_balance"], f"Running Balance — {lvl.title()}", "Balance ($)", CHARTS_DIR / f"running_balance_{lvl}.png")
    
    print("✅ Scenarios generated, charts saved to charts/, and data written to Google Sheets.")


# --------------------------
# Main CLI
# --------------------------

def main():
    ap = argparse.ArgumentParser(description="Finance-tracker CLI")
    sub = ap.add_subparsers(dest="cmd")

    p_clean = sub.add_parser("clean", help="Run cleaning pipeline; preview or save")
    p_clean.add_argument("--preview", action="store_true",
                         help="Preview cleaned dataframe head()")
    p_clean.add_argument("--save", action="store_true",
                         help="Persist cleaned ledger (CSV or Sheet tab)")
    p_clean.add_argument("--to-csv", action="store_true",
                         help="Save to charts/cleaned_preview.csv (default if --save is used)")
    p_clean.add_argument("--to-sheet", action="store_true",
                         help="Save to Google Sheet tab Ledger_CLEAN instead of CSV")

    p_charts = sub.add_parser("charts", help="Generate charts")
    p_charts.add_argument("--preview", action="store_true",
                          help="Show charts interactively instead of saving to PNGs")

    p_sync = sub.add_parser("sync-cal", help="Preview sync of posted rows to Google Calendar")
    p_sync.add_argument("--write", action="store_true", help="(Preview only for now)")

    sub.add_parser("scenarios", help="Generate demo scenarios and charts")

    args = ap.parse_args()

    if args.cmd == "clean":
        preview = bool(args.preview) or not args.save
        save = bool(args.save)
        save_to_csv = True if (args.to_csv or not args.to_sheet) else False
        cmd_clean(preview=preview, save=save, save_to_csv=save_to_csv)
    elif args.cmd == "charts":
        cmd_charts(preview=args.preview)
    elif args.cmd == "sync-cal":
        dry = not getattr(args, "write", False)
        cmd_sync_cal(dry_run=dry)
    elif args.cmd == "scenarios":
        cmd_scenarios()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
