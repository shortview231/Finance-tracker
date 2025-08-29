# tracker/charts.py
# Charts: daily net, running balance, expenses by category (pie)
# Uses ONLY cleaned/normalized columns: date_dt, amount_num, type_norm, category_norm, amount_signed

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# --------------------------
# Utilities
# --------------------------

REQUIRED_BASE = {"date_dt", "amount_num", "type_norm", "category_norm"}

def _ensure_outdir(path: str | os.PathLike) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p

def _require_cols(df: pd.DataFrame, cols: set[str]) -> None:
    missing = cols - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns for charts: {sorted(missing)}")

def _ensure_amount_signed(df: pd.DataFrame) -> pd.Series:
    """Return amount_signed; compute on the fly if missing."""
    if "amount_signed" in df.columns:
        return df["amount_signed"].astype(float)
    # Compute from amount_num + type_norm
    sign = np.where(df["type_norm"].astype(str).str.lower().eq("income"), 1.0,
                    np.where(df["type_norm"].astype(str).str.lower().eq("expense"), -1.0, 1.0))
    return df["amount_num"].astype(float) * sign

def _clean_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Safe copy, drop NAs in date, coerce types, and ensure normalized columns exist."""
    _require_cols(df, REQUIRED_BASE)
    out = df.copy()

    # Coerce types
    out["date_dt"] = pd.to_datetime(out["date_dt"], errors="coerce")
    out["amount_num"] = pd.to_numeric(out["amount_num"], errors="coerce")
    out["type_norm"] = out["type_norm"].astype("string").str.lower().str.strip()
    out["category_norm"] = out["category_norm"].astype("string").str.lower().str.strip()

    # Drop rows without usable date or amount
    out = out.dropna(subset=["date_dt", "amount_num"])

    # Ensure amount_signed
    out["amount_signed"] = _ensure_amount_signed(out)

    # Fill blanks to avoid groupby issues
    out["category_norm"] = out["category_norm"].replace("", "misc").fillna("misc")
    out["type_norm"] = out["type_norm"].replace("", pd.NA)

    return out


# --------------------------
# Chart rendering
# --------------------------

def plot_daily_net(df: pd.DataFrame, outdir: Path) -> Path:
    """Bar chart of daily net (sum of amount_signed per date)."""
    d = _clean_frame(df)

    daily = (
        d.groupby(d["date_dt"].dt.date, dropna=False)["amount_signed"]
        .sum()
        .sort_index()
    )

    fig, ax = plt.subplots(figsize=(10, 5))
    daily.plot(kind="bar", ax=ax)
    ax.set_title("Daily Net")
    ax.set_xlabel("Date")
    ax.set_ylabel("Net ($)")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()

    outpath = outdir / "daily_net.png"
    fig.savefig(outpath, dpi=144)
    plt.close(fig)
    return outpath


def plot_running_balance(df: pd.DataFrame, outdir: Path, starting_balance: float = 0.0) -> Path:
    """Line chart of running balance over time (cumulative sum of amount_signed)."""
    d = _clean_frame(df).sort_values("date_dt")

    daily = (
        d.groupby(d["date_dt"].dt.date, dropna=False)["amount_signed"]
        .sum()
        .sort_index()
        .astype(float)
    )
    running = daily.cumsum() + float(starting_balance)

    fig, ax = plt.subplots(figsize=(10, 5))
    running.plot(ax=ax)
    ax.set_title("Running Balance")
    ax.set_xlabel("Date")
    ax.set_ylabel("Balance ($)")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    outpath = outdir / "running_balance.png"
    fig.savefig(outpath, dpi=144)
    plt.close(fig)
    return outpath


def plot_expenses_pie(df: pd.DataFrame, outdir: Path, min_slice_pct: float = 2.0) -> Path:
    """
    Pie chart of total expenses by category (uses only rows where type_norm == 'expense').
    Uses positive magnitudes for readability.
    Small slices are grouped into 'other' if below min_slice_pct (% of total).
    """
    d = _clean_frame(df)
    exp = d[d["type_norm"].eq("expense")].copy()
    if exp.empty:
        # Create an empty placeholder chart so the file still exists.
        fig, ax = plt.subplots(figsize=(6, 6))
        ax.text(0.5, 0.5, "No expense data", ha="center", va="center")
        ax.axis("off")
        outpath = outdir / "expenses_pie.png"
        fig.savefig(outpath, dpi=144)
        plt.close(fig)
        return outpath

    # Use magnitudes for expenses (amount_signed is negative for expenses)
    exp["value"] = exp["amount_signed"].abs()

    by_cat = (
        exp.groupby("category_norm", dropna=False)["value"]
        .sum()
        .sort_values(ascending=False)
    )

    total = by_cat.sum()
    if total <= 0:
        # Avoid divide-by-zero; just emit placeholder
        fig, ax = plt.subplots(figsize=(6, 6))
        ax.text(0.5, 0.5, "No expense totals", ha="center", va="center")
        ax.axis("off")
        outpath = outdir / "expenses_pie.png"
        fig.savefig(outpath, dpi=144)
        plt.close(fig)
        return outpath

    # Combine very small slices into "other"
    pct = (by_cat / total) * 100.0
    large = pct[pct >= float(min_slice_pct)]
    small = pct[pct < float(min_slice_pct)]
    if not small.empty:
        large["other"] = small.sum()
        by_cat = large.sort_values(ascending=False) * (total / 100.0)

    fig, ax = plt.subplots(figsize=(7.5, 7.5))
    ax.pie(by_cat.values, labels=by_cat.index, autopct="%1.1f%%", startangle=90)
    ax.set_title("Expenses by Category")
    fig.tight_layout()

    outpath = outdir / "expenses_pie.png"
    fig.savefig(outpath, dpi=144)
    plt.close(fig)
    return outpath


# --------------------------
# Public entrypoint
# --------------------------

def render_all(df: pd.DataFrame, outdir: str | os.PathLike = "charts", starting_balance: float = 0.0) -> dict[str, Path]:
    """
    Render all milestone charts using normalized columns.
    Returns dict of chart name -> path.
    """
    od = _ensure_outdir(outdir)
    out = {}
    out["daily_net"] = plot_daily_net(df, od)
    out["running_balance"] = plot_running_balance(df, od, starting_balance=starting_balance)
    out["expenses_pie"] = plot_expenses_pie(df, od)
    return out

# --------------------------
# Optional helpers for tracker_api.py
# --------------------------

def _month_frame(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return monthly totals with columns: month, income, expense, net.
    Uses normalized columns: date_dt, amount_num, type_norm.
    """
    d = _clean_frame(df).copy()
    if d.empty:
        return pd.DataFrame(columns=["month", "income", "expense", "net"])

    d["month"] = d["date_dt"].dt.to_period("M").dt.to_timestamp()

    inc = d[d["type_norm"].eq("income")].groupby("month")["amount_num"].sum().rename("income")
    exp = d[d["type_norm"].eq("expense")].groupby("month")["amount_num"].sum().rename("expense")

    out = pd.concat([inc, exp], axis=1).fillna(0.0).reset_index()
    # expenses are positive magnitudes above; net = income - expense
    out["net"] = out["income"] - out["expense"]
    out = out.sort_values("month")
    return out


def extra_charts(df: pd.DataFrame, outdir: str | os.PathLike = "charts") -> None:
    """
    Optional charts:
      - Monthly net (bar)
      - Expenses by payment method (pie) if payment_method_norm exists
      - Bucket pie (if 'bucket' exists)
    """
    od = _ensure_outdir(outdir)
    d = _clean_frame(df)

    # 1) Monthly net
    mf = _month_frame(d)
    if not mf.empty:
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.bar(mf["month"].dt.strftime("%Y-%m"), mf["net"])
        ax.set_title("Monthly Net")
        ax.set_xlabel("Month")
        ax.set_ylabel("Net ($)")
        plt.xticks(rotation=45, ha="right")
        ax.grid(True, axis="y", alpha=0.3)
        fig.tight_layout()
        fig.savefig(Path(od) / "monthly_net.png", dpi=144)
        plt.close(fig)

    # 2) Expenses by payment method (optional)
    if "payment_method_norm" in d.columns:
        exp = d[d["type_norm"].eq("expense")].copy()
        if not exp.empty:
            exp["value"] = exp["amount_signed"].abs()
            pm = exp.groupby("payment_method_norm")["value"].sum().sort_values(ascending=False)
            if not pm.empty:
                fig, ax = plt.subplots(figsize=(7, 7))
                ax.pie(pm.values, labels=pm.index, autopct="%1.1f%%", startangle=90)
                ax.set_title("Expenses by Payment Method")
                fig.tight_layout()
                fig.savefig(Path(od) / "expenses_by_payment_method.png", dpi=144)
                plt.close(fig)

    # 3) Bucket pie (optional)
    if "bucket" in d.columns:
        exp = d[d["type_norm"].eq("expense")].copy()
        if not exp.empty:
            exp["value"] = exp["amount_signed"].abs()
            by_bucket = exp.groupby("bucket")["value"].sum().sort_values(ascending=False)
            if not by_bucket.empty:
                fig, ax = plt.subplots(figsize=(7, 7))
                ax.pie(by_bucket.values, labels=by_bucket.index, autopct="%1.1f%%", startangle=90)
                ax.set_title("Expenses by Bucket")
                fig.tight_layout()
                fig.savefig(Path(od) / "expenses_by_bucket.png", dpi=144)
                plt.close(fig)
