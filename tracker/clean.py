# tracker/clean.py
# Unified cleaning utilities for Finance-Tracker
# - Column & text normalization
# - Date/amount coercion
# - Type normalization -> income/expense
# - Category/payment method canonicalization
# - Posted -> boolean
# - Signed amounts (+ income, − expense)
# - Needs/Wants/Savings/Taxes bucket
# - Validation + optional unmapped reports

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional, Iterable, Mapping

import numpy as np
import pandas as pd

__all__ = [
    "normalize_columns",
    "lowercase_strings",
    "normalize_type",
    "coerce_date",
    "coerce_amount",
    "normalize_simple",
    "coerce_bool",
    "make_amount_signed",
    "fill_unknowns",
    "report_unmapped",
    "validate_ledger",
    "apply_bucket",
    "clean_ledger",
]

# -------------------------------------------------------------------
# Config / constants
# -------------------------------------------------------------------

TEXT_DTYPES = ("object", "string")

# Toggle debug prints
DEBUG_DATES = False
DEBUG_UNMAPPED = True

# --- Canonical category mapping (free-text -> stable bucket) ---
CATEGORY_MAP: Mapping[Iterable[str] | str, str] = {
    # INCOME
    ("income", "salary", "paycheck", "pay", "tips", "bonus", "deposit", "refund"): "income",
    ("doordash", "door dash", "doo dash", "dash", "amazon flex", "flex", "gig"): "income",
    ("transfer in", "bank transfer in"): "income",

    # HOUSING
    ("rent", "mortgage", "lease"): "housing",
    ("ameren", "electric", "electricity", "natural gas", "gas bill", "water", "trash", "internet", "wifi", "utilities"): "housing",

    # TRANSPORTATION
    ("gas", "fuel", "parking", "car payment", "car note", "car insurance", "maintenance",
     "uber", "lyft", "rideshare", "transit", "bus", "metro"): "transportation",

    # GROCERIES
    ("groceries", "grocery", "sam's", "sams", "sam’s", "aldi", "walmart food", "schnucks",
     "dollar general", "household staples"): "groceries",

    # DINING
    ("restaurant", "restaurants", "takeout", "fast food", "coffee", "starbucks",
     "mcdonalds", "taco bell", "food out", "dirt cheap"): "dining",  # Dirt Cheap -> dining/alcohol

    # HEALTH
    ("doctor", "dentist", "therapy", "pharmacy", "prescriptions", "rx", "gym", "fitness"): "health",
    ("weed", "cannabis", "natures med", "nature's med", "medical cannabis"): "health",

    # KIDS & FAMILY
    ("school", "supplies", "childcare", "daycare", "kids", "family activity"): "kids & family",

    # SUBSCRIPTIONS & SOFTWARE
    ("openai", "netflix", "spotify", "prime", "hulu", "max", "apple one",
     "subscription", "subscriptions", "sub", "adobe", "microsoft 365"): "subscriptions & software",

    # DEBT & BANKING
    ("loan payment", "credit card", "cc payment", "minimum payment", "overdraft fee",
     "bank fee", "interest", "late fee"): "debt & banking",

    # PERSONAL / SHOPPING
    ("personal", "shopping", "clothes", "household", "qol", "quality of life", "gift", "gifts"): "personal / shopping",

    # ENTERTAINMENT
    ("entertainment", "movies", "fun", "games", "concerts", "hobbies"): "entertainment",

    # SAVINGS & INVESTING
    ("savings", "transfer to savings", "brokerage", "investing", "roth", "ira", "401k"): "savings & investing",

    # TAXES
    ("tax", "taxes", "quarterly tax", "irs", "state tax", "tax penalty", "property tax"): "taxes",

    # BUSINESS (optional)
    ("business", "equipment", "supplies", "phone (work)", "software (work)", "gig expense", "mileage"): "business",

    # FIX PLACEHOLDERS / TYPOS
    ("woek", "work"): "income",
}

# --- Payment method mapping (free-text -> stable) ---
PAYMENT_MAP: Mapping[Iterable[str] | str, str] = {
    ("debit", "debit card", "card", "rj debit"): "debit",
    ("credit", "credit card", "cc"): "credit",
    ("cash",): "cash",
    ("zelle", "venmo", "paypal", "cash app", "cashapp"): "transfer",
    ("ach", "bank transfer", "eft"): "transfer",
    ("fast pay", "fastpay", "doordash fast pay"): "fast pay",
    ("check", "cheque"): "check",
    ("n/a", "na", "none", "unknown"): "misc",
}

# --- Meta-bucket: Needs/Wants/Savings/Taxes (+ Income) ---
BUCKET_MAP: Mapping[str, str] = {
    "income": "income",
    "housing": "needs",
    "transportation": "needs",
    "groceries": "needs",
    "health": "needs",
    "kids & family": "needs",
    "debt & banking": "needs",              # move if you prefer separate
    "subscriptions & software": "wants",    # promote to "needs" per-item if essential
    "personal / shopping": "wants",
    "entertainment": "wants",
    "business": "wants",                    # or separate/reimbursable
    "savings & investing": "savings",
    "taxes": "taxes",
    "misc": "wants",
}

# -------------------------------------------------------------------
# Core normalizers
# -------------------------------------------------------------------

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Standardize header names to snake_case (trim, lowercase, replace spaces with _)."""
    out = df.copy()
    out.columns = (
        pd.Index(out.columns)
        .str.strip()
        .str.lower()
        .str.replace(r"\s+", "_", regex=True)
    )
    return out


def lowercase_strings(df: pd.DataFrame, cols: Optional[Iterable[str]] = None, make_norm_cols: bool = True) -> pd.DataFrame:
    """
    Trim spaces and lowercase selected text columns.
    - cols=None: auto-select all text-like columns
    - make_norm_cols=True: write results to new *_norm columns (non-destructive). If False, overwrite originals.
    """
    out = df.copy()
    target_cols = list(out.select_dtypes(include=TEXT_DTYPES).columns) if cols is None else list(cols)
    for c in target_cols:
        s = (
            out[c]
            .astype("string")
            .str.strip()
            .str.replace(r"\s+", " ", regex=True)
            .str.lower()
        )
        if make_norm_cols:
            out[f"{c}_norm"] = s
        else:
            out[c] = s
    return out


def normalize_type(df: pd.DataFrame, col: str = "type", out_col: Optional[str] = None) -> pd.DataFrame:
    """Normalize type column to 'income' or 'expense' in a new column (default: type_norm)."""
    income_variants = {"income", "in", "pay", "salary", "deposit", "credit"}
    expense_variants = {"expense", "exp", "bill", "debit", "purchase", "withdrawal"}
    out = df.copy()
    out_col = out_col or f"{col}_norm"

    def norm(val):
        if pd.isna(val):
            return None
        v = str(val).strip().lower()
        if v in income_variants:
            return "income"
        if v in expense_variants:
            return "expense"
        return v  # fallback
    out[out_col] = out[col].apply(norm)
    return out


def coerce_date(df: pd.DataFrame, col: str = "date", out_col: Optional[str] = None) -> pd.DataFrame:
    """
    Parse a date column into pandas datetime. Writes to a new column (default: date_dt).
    Accepts:
      - YYYY-MM-DD
      - M-D-YYYY
      - M-D  (auto-fills current year)
    Invalid parses become NaT.
    """
    out = df.copy()
    out_col = out_col or f"{col}_dt"

    s = out[col].astype("string").str.strip()
    s = s.replace({"": None, "na": None, "n/a": None, "null": None}, regex=False)

    if DEBUG_DATES:
        print("\n[DEBUG] Raw date values (repr) before parsing):")
        for i, val in enumerate(s.head(10)):
            print(f"Row {i}: {repr(val)}")

    current_year = str(datetime.now().year)

    def fix_date(val):
        if val is None or pd.isna(val):
            return val
        val = str(val).strip()
        if re.fullmatch(r"\d{1,2}-\d{1,2}-\d{4}", val) or re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", val):
            return val
        if re.fullmatch(r"\d{1,2}-\d{1,2}", val):  # MM-DD
            return f"{current_year}-{val}"
        return val

    s_fixed = s.apply(fix_date)

    if DEBUG_DATES:
        print("\n[DEBUG] Fixed date values (repr) after year-filling):")
        for i, val in enumerate(s_fixed.head(10)):
            print(f"Row {i}: {repr(val)}")

    out[out_col] = pd.to_datetime(s_fixed, errors="coerce")
    return out


def coerce_amount(df: pd.DataFrame, col: str = "amount", out_col: Optional[str] = None) -> pd.DataFrame:
    """
    Clean and convert an amount column to float.
      - Removes $, commas, spaces.
      - Treats blanks, '---', 'na', 'n/a', 'null' as 0.
      - Converts (123.45) to -123.45.
      - Writes to a new column (default: amount_num).
    """
    out = df.copy()
    out_col = out_col or f"{col}_num"

    s = out[col].astype("string").str.strip()
    s = s.replace({"": "0", "---": "0", "na": "0", "n/a": "0", "null": "0"}, regex=False)
    s = s.str.replace(r"[$,]", "", regex=True)
    s = s.str.replace(r"\(([^)]+)\)", r"-\1", regex=True)  # (123.45) -> -123.45
    s = s.str.replace(" ", "", regex=False)
    out[out_col] = pd.to_numeric(s, errors="coerce").fillna(0)
    return out

# -------------------------------------------------------------------
# Category / payment canonicalization
# -------------------------------------------------------------------

def _build_canon_map(mapping: Mapping[Iterable[str] | str, str]) -> dict[str, str]:
    canon: dict[str, str] = {}
    for keys, val in mapping.items():
        if isinstance(keys, (list, tuple, set)):
            for k in keys:
                canon[str(k).lower()] = val
        else:
            canon[str(keys).lower()] = mapping[keys]  # type: ignore[index]
    return canon


def normalize_simple(df: pd.DataFrame, col: str, mapping: Optional[Mapping[Iterable[str] | str, str]] = None, out_col: Optional[str] = None) -> pd.DataFrame:
    """Lowercase/trim a text column and optionally map common variants/typos to canonical values."""
    out = df.copy()
    out_col = out_col or f"{col}_norm"
    s = out[col].astype("string").str.strip().str.replace(r"\s+", " ", regex=True).str.lower()

    if mapping:
        canon = _build_canon_map(mapping)
        s = s.map(lambda v: canon.get(v, v))

    out[out_col] = s
    return out


def coerce_bool(df: pd.DataFrame, col: str = "posted", out_col: Optional[str] = None) -> pd.DataFrame:
    """Normalize a yes/no style column to boolean True/False/NA."""
    out = df.copy()
    out_col = out_col or f"{col}_bool"
    true_vals = {"true", "t", "yes", "y", "1", "paid"}
    false_vals = {"false", "f", "no", "n", "0", "unpaid", ""}
    s = out[col].astype("string").str.strip().str.lower().fillna("")
    out[out_col] = s.map(lambda v: True if v in true_vals else (False if v in false_vals else pd.NA))
    return out


def make_amount_signed(df: pd.DataFrame, amount_col: str = "amount_num", type_col: str = "type_norm", out_col: str = "amount_signed") -> pd.DataFrame:
    """Apply +/− sign to amounts depending on type_norm."""
    out = df.copy()

    def sign_row(row):
        amt = row.get(amount_col, np.nan)
        t = str(row.get(type_col, "")).lower()
        if pd.isna(amt):
            return np.nan
        if t == "income":
            return float(amt)
        if t == "expense":
            return -float(amt)
        return float(amt)

    out[out_col] = out.apply(sign_row, axis=1)
    return out


def fill_unknowns(df: pd.DataFrame, cols: Iterable[str] = ("category_norm", "payment_method_norm")) -> pd.DataFrame:
    """Fill blanks/NaNs with 'misc' so charts and groupbys don't choke."""
    out = df.copy()
    for c in cols:
        if c in out.columns:
            out[c] = out[c].fillna("misc")
            out.loc[out[c].astype("string").str.strip().eq(""), c] = "misc"
    return out


def report_unmapped(df: pd.DataFrame) -> None:
    """Print a quick list of still-unmapped labels so maps can be extended over time."""
    if not DEBUG_UNMAPPED:
        return

    def _unmapped(raw_col: str, norm_col: str, label: str):
        if raw_col in df.columns and norm_col in df.columns:
            raw = df[raw_col].astype("string").str.lower().str.strip()
            norm = df[norm_col].astype("string").str.lower().str.strip()
            not_mapped = raw.eq(norm) & raw.ne("")
            if not_mapped.any():
                print(f"\n[UNMAPPED] {label} values (top 20 by frequency):")
                print(raw[not_mapped].value_counts().head(20))

    _unmapped("category", "category_norm", "category")
    _unmapped("payment_method", "payment_method_norm", "payment_method")

# -------------------------------------------------------------------
# Validation, buckets, and pipeline
# -------------------------------------------------------------------

REQUIRED_COLS = {"date", "type", "amount"}

def validate_ledger(df: pd.DataFrame) -> None:
    """Check required cols, missing values, and duplicates."""
    missing = REQUIRED_COLS - set(map(str.lower, df.columns))
    if missing:
        raise ValueError(f"Ledger missing required columns: {sorted(missing)}")
    # light reporting
    print("[VALIDATION] Missing values per column:\n", df.isna().sum())
    dups = df.duplicated().sum()
    if dups:
        print(f"[VALIDATION] Warning: {dups} duplicate rows detected.")


def apply_bucket(df: pd.DataFrame, cat_col: str = "category_norm", out_col: str = "bucket") -> pd.DataFrame:
    """Map category_norm/type_norm into a coarse bucket: needs/wants/savings/taxes/income."""
    out = df.copy()
    if cat_col in out.columns:
        out[out_col] = out[cat_col].map(lambda v: BUCKET_MAP.get(str(v), "wants"))
    # Ensure income rows are bucketed as income
    if "type_norm" in out.columns:
        out.loc[out["type_norm"].eq("income"), out_col] = "income"
    return out


def clean_ledger(df: pd.DataFrame) -> pd.DataFrame:
    """Run full cleaning pipeline, return ready-to-analyze frame."""
    # 1) normalize headers, validate minimal shape
    df1 = normalize_columns(df)
    validate_ledger(df1)

    # 2) non-destructive text normalization (adds *_norm for all text cols)
    df2 = lowercase_strings(df1, make_norm_cols=True)

    # 3) type normalization and numeric/date coercions
    df3 = normalize_type(df2, col="type", out_col="type_norm")
    df4 = coerce_amount(df3, col="amount", out_col="amount_num")
    df5 = coerce_date(df4, col="date", out_col="date_dt")

    # 4) posted flag
    if "posted" in df5.columns:
        df5 = coerce_bool(df5, col="posted", out_col="posted_bool")

    # 5) category & payment canonicalization to stable buckets
    if "category" in df5.columns:
        df5 = normalize_simple(df5, "category", CATEGORY_MAP, "category_norm")
    if "payment_method" in df5.columns:
        df5 = normalize_simple(df5, "payment_method", PAYMENT_MAP, "payment_method_norm")
    df5 = fill_unknowns(df5)

    # 6) signed amounts
    df6 = make_amount_signed(df5, amount_col="amount_num", type_col="type_norm", out_col="amount_signed")

    # 7) Needs/Wants/Savings/Taxes bucket
    df7 = apply_bucket(df6)

    # 8) optional report of unmapped labels
    report_unmapped(df7)

    return df7
