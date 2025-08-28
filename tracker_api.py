# tracker_api.py
# CLI for Finance-tracker: clean data, make charts, preview sync-cal & scenarios
import argparse
from pathlib import Path
from typing import Tuple

import pandas as pd
import matplotlib.pyplot as plt

from tracker.clean import (
    clean_ledger,
    validate_ledger,
)
from tracker.io import read_ledger_from_sheets  # and optionally write_df_to_sheet

CHARTS_DIR = Path("charts")
CHARTS_DIR.mkdir(parents=True, exist_ok=True)

RUNNING_BALANCE_PNG = CHARTS_DIR / "running_balance.png"
DAILY_NET_PNG = CHARTS_DIR / "daily_net.png"
EXPENSES_PIE_PNG = CHARTS_DIR / "expenses_pie.png"
CLEANED_PREVIEW_CSV = CHARTS_DIR / "cleaned_preview.csv"


# --------------------------
# Helpers
# --------------------------
def _load_clean_df(prefer_csv: bool = True) -> pd.DataFrame:
    """
    Load a cleaned dataframe:
      - if charts/cleaned_preview.csv exists and prefer_csv=True, load it;
      - else read raw ledger from Sheets and run the full clean_ledger pipeline.
    Ensures the returned frame has: date_dt, type_norm, amount_num, amount_signed (and best-effort posted_bool/category_norm).
    """
    if prefer_csv and CLEANED_PREVIEW_CSV.exists():
        print(f"ℹ️ Using cleaned preview CSV → {CLEANED_PREVIEW_CSV}")
        df = pd.read_csv(CLEANED_PREVIEW_CSV)
        # best-effort ensure dtypes
        if "date_dt" in df.columns:
            df["date_dt"] = pd.to_datetime(df["date_dt"], errors="coerce")
        if "amount_num" in df.columns:
            df["amount_num"] = pd.to_numeric(df["amount_num"], errors="coerce")
        if "amount_signed" in df.columns:
            df["amount_signed"] = pd.to_numeric(df["amount_signed"], errors="coerce")
        return df

    print("ℹ️ No cleaned_preview.csv (or bypassed) — reading raw ledger from Sheets and cleaning.")
    raw = read_ledger_from_sheets()
    df = clean_ledger(raw)
    return df


def _save_clean_preview_csv(df: pd.DataFrame, path: Path = CLEANED_PREVIEW_CSV):
    df_out = df.copy()
    # Save friendly string dates
    if "date_dt" in df_out.columns:
        df_out["date_dt"] = df_out["date_dt"].dt.strftime("%Y-%m-%d")
    df_out.to_csv(path, index=False)
    print(f"✅ Saved cleaned preview to {path}")


def _require_columns(df: pd.DataFrame, cols: Tuple[str, ...]):
    missing = set(cols) - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


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
    """
    raw = read_ledger_from_sheets()
    dfc = clean_ledger(raw)

    # validation echo
    try:
        validate_ledger(dfc)
    except Exception as e:
        print(f"⚠️ Validation check raised: {e}")

    # PREVIEW BLOCKS
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
            tmp["date_dt"] = tmp["date_dt"].dt.strftime("%Y-%m-%d")
        print(tmp.head(10))
        if "date_dt" in dfc.columns:
            bad_dates = dfc[dfc["date_dt"].isna()]
            if not bad_dates.empty:
                print("\n=== Bad Dates (failed parse) ===")
                print(bad_dates[["date"]].head(20))

    # Posted
    if "posted" in dfc.columns or "posted_bool" in dfc.columns:
        print("\n=== Posted Preview ===")
        cols_post = [c for c in ["posted", "posted_bool"] if c in dfc.columns]
        print(dfc[cols_post].head(10))

    # Category
    cat_cols = [c for c in ["category", "category_norm"] if c in dfc.columns]
    if cat_cols:
        print("\n=== Category Preview ===")
        print(dfc[cat_cols].head(10))

    # Persist if asked
    if save:
        if save_to_csv:
            _save_clean_preview_csv(dfc, Path(csv_path))
        else:
            try:
                from tracker.io import write_df_to_sheet
                # Save a sheet-friendly copy (string dates)
                df_sheet = dfc.copy()
                if "date_dt" in df_sheet.columns:
                    df_sheet["date_dt"] = df_sheet["date_dt"].dt.strftime("%Y-%m-%d")
                write_df_to_sheet(df_sheet, tab_name=sheet_tab)
                print(f"✅ Wrote cleaned preview to Sheet tab: {sheet_tab}")
            except ImportError:
                print("⚠️ write_df_to_sheet not found in tracker.io — CSV fallback recommended.")


# --------------------------
# CHARTS command
# --------------------------
def _daily_frames_from_clean(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Build daily net and running balance from cleaned columns.
    Requires: date_dt (datetime), amount_signed (float)
    """
    _require_columns(df, ("date_dt", "amount_signed"))

    wk = df.dropna(subset=["date_dt", "amount_signed"]).copy()
    # normalize to date (no time)
    wk["date"] = wk["date_dt"].dt.date
    # daily net = sum of signed amounts per day
    daily = wk.groupby("date", dropna=True)["amount_signed"].sum().rename("net").reset_index()

    # running balance (cumulative sum in chronological order)
    daily_sorted = daily.sort_values("date").reset_index(drop=True)
    daily_sorted["running_balance"] = daily_sorted["net"].cumsum()

    return daily_sorted[["date", "net"]], daily_sorted[["date", "running_balance"]]


def _plot_line(x, y, title: str, ylabel: str, outfile: Path):
    plt.figure()
    plt.plot(x, y)
    plt.title(title)
    plt.xlabel("Date")
    plt.ylabel(ylabel)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(outfile, dpi=160)
    plt.close()
    print(f"✅ Saved {outfile}")


def _plot_pie(series: pd.Series, title: str, outfile: Path):
    plt.figure()
    series.plot(kind="pie", autopct="%1.0f%%")
    plt.ylabel("")
    plt.title(title)
    plt.tight_layout()
    plt.savefig(outfile, dpi=160)
    plt.close()
    print(f"✅ Saved {outfile}")


def cmd_charts():
    df = _load_clean_df(prefer_csv=True)

    # Daily + Running Balance from signed amounts
    daily, run = _daily_frames_from_clean(df)
    _plot_line(daily["date"], daily["net"], "Daily Net", "Net ($)", DAILY_NET_PNG)
    _plot_line(run["date"], run["running_balance"], "Running Balance", "Balance ($)", RUNNING_BALANCE_PNG)

    # Expenses pie: prefer category_norm; fallback to category
    cat_col = "category_norm" if "category_norm" in df.columns else ("category" if "category" in df.columns else None)
    if cat_col is None:
        print("ℹ️ No category/category_norm column found; skipping expenses pie.")
        return

    # Only expenses (amount_signed < 0)
    exp = df[df["amount_signed"] < 0].copy()
    if exp.empty:
        print("ℹ️ No expense rows found; skipping expenses pie.")
        return

    exp["abs_amount"] = exp["amount_signed"].abs()
    by_cat = exp.groupby(cat_col, dropna=True)["abs_amount"].sum().sort_values(ascending=False)

    if by_cat.empty:
        print("ℹ️ No expense data grouped; skipping expenses pie.")
        return

    if len(by_cat) > 8:
        top = by_cat.head(8)
        other = pd.Series({"Other": by_cat.iloc[8:].sum()})
        pie_data = pd.concat([top, other])
    else:
        pie_data = by_cat

    _plot_pie(pie_data, "Expenses by Category", EXPENSES_PIE_PNG)


# --------------------------
# SYNC-CAL command (previewable)
# --------------------------
def _preview_calendar_payloads(df: pd.DataFrame, max_rows: int = 10):
    """
    Build preview of calendar event titles from cleaned rows with posted_bool == True.
    """
    if "posted_bool" not in df.columns:
        print("ℹ️ posted_bool not present; nothing to sync.")
        return []

    rows = df[(df["posted_bool"] == True) & df["date_dt"].notna()].copy()
    if rows.empty:
        print("ℹ️ No posted==True rows to sync.")
        return []

    # event title preview: "Income • DoorDash ($45.50)" or "Expense • Rent ($1450.00)"
    def title_for(r):
        t = str(r.get("type_norm", "")).title() or "Txn"
        src = r.get("source") or r.get("description") or ""
        amt = r.get("amount_num", r.get("amount_signed", 0.0))
        try:
            amt = float(amt)
        except Exception:
            amt = 0.0
        if t.lower() == "expense" and amt > 0:
            amt = -amt  # ensure expense shows negative if mis-signed
        return f"{t} • {src} (${abs(amt):,.2f})".strip()

    rows = rows.sort_values("date_dt")
    previews = []
    for _, r in rows.head(max_rows).iterrows():
        previews.append({
            "date": r["date_dt"].date().isoformat(),
            "title": title_for(r),
            "category": r.get("category_norm", r.get("category", "")),
            "payment_method": r.get("payment_method_norm", r.get("payment_method", "")),
        })

    print("\n=== Calendar Sync Preview (first up to 10) ===")
    for p in previews:
        print(f"{p['date']}  —  {p['title']}  [{p['category']}]  ({p['payment_method']})")

    if len(rows) > max_rows:
        print(f"… and {len(rows) - max_rows} more posted rows ready.")

    return previews


def cmd_sync_cal(dry_run: bool = True):
    """
    Preview (or later: write) Google Calendar events for posted rows.
    Currently: preview only. When write-mode is implemented, we'll call tracker.io calendar helpers.
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
    Create a tiny synthetic ledger for demo charts.
    month: '2025-08' style
    income_level: 'low' | 'medium' | 'high'
    """
    import numpy as np
    rng = pd.date_range(f"{month}-01", periods=28, freq="D")
    base_income = {"low": 50, "medium": 120, "high": 220}[income_level]
    noise = {"low": 25, "medium": 50, "high": 80}[income_level]

    df = pd.DataFrame({
        "date": rng.strftime("%Y-%m-%d"),
        "type": np.where(rng.day % 3 == 0, "income", "expense"),
        "category": np.where(rng.day % 3 == 0, "gig", np.where(rng.day % 2 == 0, "groceries", "gas")),
        "amount": np.where(rng.day % 3 == 0, base_income + np.random.randint(-10, 10),
                           -(noise + np.random.randint(0, 40))),
        "source": np.where(rng.day % 3 == 0, "demo", ""),
        "posted": "true",
    })
    return clean_ledger(df)


def cmd_scenarios():
    print("📊 Generating demo scenarios (low/medium/high)…")
    for lvl in ("low", "medium", "high"):
        df_demo = _synthesize_demo_ledger("2025-08", lvl)
        daily, run = _daily_frames_from_clean(df_demo)
        _plot_line(daily["date"], daily["net"], f"Daily Net — {lvl.title()}", "Net ($)", CHARTS_DIR / f"daily_net_{lvl}.png")
        _plot_line(run["date"], run["running_balance"], f"Running Balance — {lvl.title()}", "Balance ($)", CHARTS_DIR / f"running_balance_{lvl}.png")
    print("✅ Scenarios generated to charts/ (three pairs of PNGs).")


# --------------------------
# Main CLI
# --------------------------
def main():
    ap = argparse.ArgumentParser(description="Finance-tracker CLI")
    sub = ap.add_subparsers(dest="cmd")

    p_clean = sub.add_parser("clean", help="Run cleaning pipeline; optionally save a cleaned preview")
    p_clean.add_argument("--save", action="store_true",
                         help="Persist cleaned preview (CSV or Sheet tab)")
    p_clean.add_argument("--to-csv", action="store_true",
                         help="Save to charts/cleaned_preview.csv (default if --save is used)")
    p_clean.add_argument("--to-sheet", action="store_true",
                         help="Save to Google Sheet tab Ledger_CLEAN instead of CSV")

    sub.add_parser("charts", help="Generate daily net, running balance, and expenses pie charts")

    p_sync = sub.add_parser("sync-cal", help="Preview sync of posted rows to Google Calendar")
    p_sync.add_argument("--write", action="store_true", help="(Preview only for now)")

    sub.add_parser("scenarios", help="Generate demo scenarios and charts")

    args = ap.parse_args()

    if args.cmd == "clean":
        save = bool(args.save)
        save_to_csv = True if (args.to_csv or not args.to_sheet) else False
        cmd_clean(preview=not save, save=save, save_to_csv=save_to_csv)
    elif args.cmd == "charts":
        cmd_charts()
    elif args.cmd == "sync-cal":
        dry = not getattr(args, "write", False)
        cmd_sync_cal(dry_run=dry)
    elif args.cmd == "scenarios":
        cmd_scenarios()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
