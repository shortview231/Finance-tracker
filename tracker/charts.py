# tracker/charts.py
# Extra charts that build on the cleaned ledger produced by tracker.clean.clean_ledger

from __future__ import annotations

from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt


def _plot_pie(series: pd.Series, title: str, outfile: Path):
    if series is None or series.empty:
        return
    plt.figure()
    series.plot(kind="pie", autopct="%1.0f%%")
    plt.ylabel("")
    plt.title(title)
    plt.tight_layout()
    plt.savefig(outfile, dpi=160)
    plt.close()
    print(f"✅ Saved {outfile}")


def _plot_bars(x, cols_to_series: dict, title: str, ylabel: str, outfile: Path):
    plt.figure()
    width = 0.25
    xs = range(len(x))
    keys = list(cols_to_series.keys())
    for i, k in enumerate(keys):
        plt.bar([p + i * width for p in xs], cols_to_series[k], width=width, label=k.title())
    # label months as YYYY-MM
    labels = []
    for d in x:
        try:
            labels.append(str(pd.to_datetime(d))[:7])
        except Exception:
            labels.append(str(d))
    plt.xticks([p + width for p in xs], labels, rotation=45, ha="right")
    plt.title(title)
    plt.ylabel(ylabel)
    plt.legend()
    plt.tight_layout()
    plt.savefig(outfile, dpi=160)
    plt.close()
    print(f"✅ Saved {outfile}")


def _month_frame(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build a monthly rollup: income, expense, net.
    Requires columns: date_dt (datetime-like), amount_signed (float).
    """
    need = {"date_dt", "amount_signed"}
    if not need.issubset(df.columns):
        raise ValueError("Missing required cleaned columns for monthly rollup: date_dt, amount_signed")

    wk = df.dropna(subset=["date_dt", "amount_signed"]).copy()
    wk["date_dt"] = pd.to_datetime(wk["date_dt"], errors="coerce")
    wk = wk.dropna(subset=["date_dt"])
    wk["month"] = wk["date_dt"].dt.to_period("M").dt.to_timestamp()

    income = wk[wk["amount_signed"] > 0].groupby("month")["amount_signed"].sum()
    expense = wk[wk["amount_signed"] < 0].groupby("month")["amount_signed"].sum().abs()

    months = sorted(set(income.index) | set(expense.index))
    out = pd.DataFrame(index=months).sort_index()
    out["income"] = income.reindex(months).fillna(0)
    out["expense"] = expense.reindex(months).fillna(0)
    out["net"] = out["income"] - out["expense"]
    out.index.name = "month"
    return out.reset_index()


def extra_charts(df: pd.DataFrame, outdir: Path):
    """
    Generate additional charts alongside the baseline ones:
      - expenses_bucket.png          (spend by needs/wants/savings/taxes)
      - monthly_totals.png           (income/expense/net per month)
      - expenses_by_payment.png      (spend by payment method)
    """
    outdir.mkdir(parents=True, exist_ok=True)

    # 1) Spending by Bucket (Needs/Wants/Savings/Taxes)
    if "bucket" in df.columns:
        spend = df[df["amount_signed"] < 0].copy()
        by_bucket = (
            spend.groupby("bucket")["amount_signed"]
            .sum()
            .abs()
            .sort_values(ascending=False)
        )
        if not by_bucket.empty:
            _plot_pie(by_bucket, "Spending by Bucket (Needs/Wants/Savings/Taxes)", outdir / "expenses_bucket.png")
        else:
            print("ℹ️ No spending rows found for bucket pie.")
    else:
        print("ℹ️ No 'bucket' column; skipping bucket pie.")

    # 2) Monthly totals: income / expense / net
    try:
        mf = _month_frame(df)
        if not mf.empty:
            _plot_bars(
                mf["month"],
                {"income": mf["income"], "expense": mf["expense"], "net": mf["net"]},
                "Monthly Totals (Income / Expense / Net)",
                "Amount ($)",
                outdir / "monthly_totals.png",
            )
        else:
            print("ℹ️ Monthly frame empty; skipping monthly_totals.png")
    except Exception as e:
        print(f"ℹ️ Skipping monthly totals: {e}")

    # 3) Expenses by Payment Method
    if "payment_method_norm" in df.columns:
        spend = df[df["amount_signed"] < 0].copy()
        by_pm = (
            spend.groupby("payment_method_norm")["amount_signed"]
            .sum()
            .abs()
            .sort_values(ascending=False)
        )
        if not by_pm.empty:
            _plot_pie(by_pm, "Expenses by Payment Method", outdir / "expenses_by_payment.png")
        else:
            print("ℹ️ No spending rows found for payment method pie.")
    else:
        print("ℹ️ No 'payment_method_norm' column; skipping payment method pie.")
