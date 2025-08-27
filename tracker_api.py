# tracker_api.py
# CLI for Finance-tracker: clean data, make charts, (stubs for sync-cal & scenarios)
import argparse
from pathlib import Path
from typing import Tuple

import pandas as pd
import matplotlib.pyplot as plt

# was: from tracker.clean import normalize_columns, lowercase_strings
# >>> ADDED: import coerce_date too
from tracker.clean import normalize_columns, lowercase_strings, coerce_date
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
def _coerce_types(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure date/amount have usable dtypes."""
    out = df.copy()
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"], errors="coerce")
    if "amount" in out.columns:
        out["amount"] = (
            pd.to_numeric(
                out["amount"].astype("string")
                .str.replace(r"[,$()\s]", "", regex=True)
                .str.replace(r"^-+$", "0", regex=True),
                errors="coerce",
            )
        )
    return out


def _require_columns(df: pd.DataFrame, cols: Tuple[str, ...]):
    missing = set(cols) - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def _prefer_clean_csv_or_sheet() -> pd.DataFrame:
    """Use cleaned_preview.csv if present; else read from Sheets and do minimal cleaning."""
    if CLEANED_PREVIEW_CSV.exists():
        print(f"ℹ️ Using cleaned preview CSV → {CLEANED_PREVIEW_CSV}")
        df = pd.read_csv(CLEANED_PREVIEW_CSV)
    else:
        print("ℹ️ No cleaned_preview.csv found — reading raw ledger from Sheets.")
        df = read_ledger_from_sheets()
        df = normalize_columns(df)
        df = lowercase_strings(df, cols=None, make_norm_cols=False)
    df = _coerce_types(df)
    return df


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
    Preview-only cleaner by default.
    Use --save to persist to CSV or to a Google Sheet tab.
    """
    # 1) load raw
    df = read_ledger_from_sheets()

    # 2) normalize columns and text (overwrite text to keep downstream simple)
    dfc = normalize_columns(df)
    dfc = lowercase_strings(dfc, cols=None, make_norm_cols=False)

    # >>> ADDED: parse date text -> datetime into a *new* column date_dt
    dfc = coerce_date(dfc, col="date", out_col="date_dt")

    # 3) coerce core types for quick stats (still keeps your original columns)
    dfc = _coerce_types(dfc)

    # 4) preview
    print("\n=== HEAD (first 8 rows) ===")
    print(dfc.head(8))

    # >>> ADDED: show date comparison and any failures
    print("\n=== Date Preview (original vs parsed) ===")
    cols_to_show = [c for c in ["date", "date_dt"] if c in dfc.columns]
    if cols_to_show:
        print(dfc[cols_to_show].head(10))
        bad_dates = dfc[dfc["date_dt"].isna()]
        if not bad_dates.empty:
            print("\n=== Bad Dates (failed parse) ===")
            print(bad_dates[["date"]].head(20))
    else:
        print("No date/date_dt columns found.")

    # 5) quick validation
    try:
        _require_columns(dfc, ("date", "type", "category", "amount"))
    except ValueError as e:
        print(f"⚠️ {e}")

    # 6) persist if asked
    if save:
        if save_to_csv:
            dfc.to_csv(csv_path, index=False)
            print(f"✅ Saved cleaned preview to {csv_path}")
        else:
            try:
                from tracker.io import write_df_to_sheet
                write_df_to_sheet(dfc, tab_name=sheet_tab)
                print(f"✅ Wrote cleaned preview to Sheet tab: {sheet_tab}")
            except ImportError:
                print("⚠️ write_df_to_sheet not found in tracker.io — CSV fallback recommended.")


# --------------------------
# CHARTS command
# --------------------------
def _daily_frames(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    _require_columns(df, ("date", "type", "amount"))
    wk = df.dropna(subset=["date", "amount"]).copy()
    wk["date"] = wk["date"].dt.date
    wk["type"] = wk["type"].astype("string").str.lower().str.strip()

    daily_income = wk.loc[wk["type"] == "income"].groupby("date", dropna=True)["amount"].sum()
    daily_expense = wk.loc[wk["type"] == "expense"].groupby("date", dropna=True)["amount"].sum()

    all_days = pd.Index(sorted(set(daily_income.index) | set(daily_expense.index)))
    daily = pd.DataFrame(index=all_days)
    daily["income"] = daily_income.reindex(all_days).fillna(0)
    daily["expense"] = daily_expense.reindex(all_days).fillna(0)
    daily["net"] = daily["income"] - daily["expense"].abs()

    run = daily.copy()
    run["running_balance"] = run["net"].cumsum()

    daily.index.name = "date"
    run.index.name = "date"
    return daily.reset_index(), run.reset_index()


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
    df = _prefer_clean_csv_or_sheet()
    _require_columns(df, ("date", "type", "category", "amount"))

    daily, run = _daily_frames(df)
    _plot_line(daily["date"], daily["net"], "Daily Net", "Net ($)", DAILY_NET_PNG)
    _plot_line(run["date"], run["running_balance"], "Running Balance", "Balance ($)", RUNNING_BALANCE_PNG)

    exp = df[df["type"].astype("string").str.lower().str.strip() == "expense"].copy()
    exp["abs_amount"] = exp["amount"].abs()
    by_cat = exp.groupby("category", dropna=True)["abs_amount"].sum().sort_values(ascending=False)

    if len(by_cat) > 8:
        top = by_cat.head(8)
        other = pd.Series({"Other": by_cat.iloc[8:].sum()})
        pie_data = pd.concat([top, other])
    else:
        pie_data = by_cat

    if pie_data.empty:
        print("ℹ️ No expense data found; skipping expenses_pie.png")
    else:
        _plot_pie(pie_data, "Expenses by Category", EXPENSES_PIE_PNG)


# --------------------------
# SYNC-CAL command (stub)
# --------------------------
def cmd_sync_cal(dry_run: bool = True):
    print("🗓️ sync-cal: stub\n- Later: read ledger; filter posted==TRUE; push events via Calendar API.")
    if dry_run:
        print("Dry-run mode: no writes performed.")


# --------------------------
# SCENARIOS command (stub)
# --------------------------
def cmd_scenarios():
    print("📊 scenarios: stub\n- Later: synthesize 3 ledgers and render charts to charts/ folder.")


# --------------------------
# Main CLI
# --------------------------
def main():
    ap = argparse.ArgumentParser(description="Finance-tracker CLI")
    sub = ap.add_subparsers(dest="cmd")

    p_clean = sub.add_parser("clean", help="Preview cleaning; optionally save a cleaned preview")
    p_clean.add_argument("--save", action="store_true",
                         help="Persist cleaned preview (CSV or Sheet tab)")
    p_clean.add_argument("--to-csv", action="store_true",
                         help="Save to charts/cleaned_preview.csv (default if --save is used)")
    p_clean.add_argument("--to-sheet", action="store_true",
                         help="Save to Google Sheet tab Ledger_CLEAN instead of CSV")

    sub.add_parser("charts", help="Generate daily net, running balance, and expenses pie charts")

    p_sync = sub.add_parser("sync-cal", help="Sync posted rows to Google Calendar (stub)")
    p_sync.add_argument("--write", action="store_true", help="Actually write events (otherwise dry-run)")

    sub.add_parser("scenarios", help="Generate demo scenarios (stub)")

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
