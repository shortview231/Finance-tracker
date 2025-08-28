# tracker/clean.py
# Unified cleaning utilities for Finance-Tracker
# - Column & text normalization + typo fixes (woek->work, etc.)
# - Date/amount coercion with strict checks
# - Type normalization -> income/expense
# - Category/payment method canonicalization
# - Posted -> boolean
# - Signed amounts (+ income, − expense)
# - Needs/Wants/Savings/Taxes bucket
# - Validation + typo suggestions (closest match)
# - Schema enforcement (optional strict mode)

from __future__ import annotations

import re
import difflib
from datetime import datetime
from typing import Optional, Iterable, Mapping, Dict, List, Tuple

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
    "report_mapped_unmapped",
    "validate_ledger",
    "apply_bucket",
    "enforce_schema",
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
    # INCOME-LIKE CATEGORIES
    ("income", "salary", "paycheck", "pay", "tips", "bonus", "deposit", "refund", "work", "woek"): "income",

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
     "mcdonalds", "taco bell", "food out", "dirt cheap"): "dining",

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
    "debt & banking": "needs",
    "subscriptions & software": "wants",
    "personal / shopping": "wants",
    "entertainment": "wants",
    "business": "wants",
    "savings & investing": "savings",
    "taxes": "taxes",
    "misc": "wants",
}

TYPE_ALLOWED = {"income", "expense"}
CATEGORY_ALLOWED = set(CATEGORY_MAP.values()) | {"misc"}  # canonical set + misc
PAYMENT_ALLOWED = set(PAYMENT_MAP.values())

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def _build_canon_map(mapping: Mapping[Iterable[str] | str, str]) -> Dict[str, str]:
    """Flatten dict[(aliases)->value] into simple dict[str->value], lowercased keys."""
    canon: dict[str, str] = {}
    for keys, val in mapping.items():
        if isinstance(keys, (list, tuple, set)):
            for k in keys:
                canon[str(k).lower()] = val
        else:
            canon[str(keys).lower()] = mapping[keys]  # type: ignore[index]
    return canon

def _closest(value: str, candidates: Iterable[str], n: int = 1) -> List[str]:
    """Return up to n close matches from candidates."""
    if not value:
        return []
    return difflib.get_close_matches(value, list(candidates), n=n, cutoff=0.6)

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


def lowercase_strings(df: pd.DataFrame, make_norm_cols: bool = False) -> pd.DataFrame:
    """Normalize text columns: lowercase, strip, collapse spaces, fix common typos on known fields.
    If make_norm_cols=True, also create *_norm for ALL text columns (safe defaults)."""
    out = df.copy()

    # Canonical typo dictionaries (known fields)
    source_map = {
        "woek": "work",
        "wrk": "work",
        "doodash": "doordash",
        "door dash": "doordash",
        "doo dash": "doordash",
    }
    category_map = {
        "woek": "work",  # ensure it normalizes before canonical mapping
        "grcoeries": "groceries",
        "grocceries": "groceries",
        "groceris": "groceries",
    }

    if "source" in out.columns:
        out["source_norm"] = (
            out["source"]
            .astype("string").str.lower().str.strip()
            .str.replace(r"\s+", " ", regex=True)
            .replace(source_map)
        )

    if "category" in out.columns:
        out["category_norm"] = (
            out["category"]
            .astype("string").str.lower().str.strip()
            .str.replace(r"\s+", " ", regex=True)
            .replace(category_map)
        )

    # Optionally create *_norm for ALL text columns (don’t overwrite ones we just set)
    if make_norm_cols:
        for c in out.columns:
            if out[c].dtype.name in TEXT_DTYPES and not c.endswith("_norm"):
                norm_c = f"{c}_norm"
                if norm_c not in out.columns:
                    out[norm_c] = (
                        out[c]
                        .astype("string").str.lower().str.strip()
                        .str.replace(r"\s+", " ", regex=True)
                    )

    return out


def normalize_type(df: pd.DataFrame, col: str = "type", out_col: Optional[str] = None) -> pd.DataFrame:
    """Normalize type column to 'income' or 'expense' in a new column (default: type_norm)."""
    out = df.copy()
    out_col = out_col or f"{col}_norm"

    income_variants = {"income", "in", "pay", "salary", "deposit", "credit"}
    expense_variants = {"expense", "exp", "bill", "debit", "purchase", "withdrawal"}

    def norm(val):
        if pd.isna(val):
            return None
        v = str(val).strip().lower()
        if v in income_variants:
            return "income"
        if v in expense_variants:
            return "expense"
        # fuzzy suggestion
        close = _closest(v, TYPE_ALLOWED, n=1)
        return close[0] if close else v  # keep unknown visible

    out[out_col] = out[col].apply(norm)
    return out


def coerce_date(df: pd.DataFrame, col: str = "date", out_col: Optional[str] = None) -> pd.DataFrame:
    """
    Parse a date column into pandas datetime. Writes to a new column (default: date_dt).
    Accepts:
      - YYYY-MM-DD
      - M-D-YYYY  (or with /)
      - M-D       (auto-fills current year)
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
        val = str(val).strip().replace("/", "-")
        if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", val):  # YYYY-M-D
            return val
        if re.fullmatch(r"\d{1,2}-\d{1,2}-\d{4}", val):  # M-D-YYYY
            m, d, y = val.split("-")
            return f"{y}-{m}-{d}"
        if re.fullmatch(r"\d{1,2}-\d{1,2}", val):        # M-D -> fill year
            m, d = val.split("-")
            return f"{current_year}-{m}-{d}"
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
    Clean and convert an amount column to float (idempotent).
      - Leaves numeric as-is.
      - Removes $, commas, spaces.
      - Treats blanks, '---', 'na', 'n/a', 'null' as 0.
      - Converts (123.45) to -123.45.
      - Writes to a new column (default: amount_num).
    """
    out = df.copy()
    out_col = out_col or f"{col}_num"

    s = out[col]
    if np.issubdtype(s.dtype, np.number):
        out[out_col] = pd.to_numeric(s, errors="coerce").fillna(0.0)
        return out

    s = s.astype("string").str.strip()
    s = s.replace({"": "0", "---": "0", "na": "0", "n/a": "0", "null": "0"}, regex=False)
    s = s.str.replace(r"[$,]", "", regex=True)
    s = s.str.replace(r"\(([^)]+)\)", r"-\1", regex=True)  # (123.45) -> -123.45
    s = s.str.replace(" ", "", regex=False)
    out[out_col] = pd.to_numeric(s, errors="coerce").fillna(0.0)
    return out

# -------------------------------------------------------------------
# Category / payment canonicalization
# -------------------------------------------------------------------

def normalize_simple(
    df: pd.DataFrame,
    col: str,
    mapping: Optional[Mapping[Iterable[str] | str, str]] = None,
    out_col: Optional[str] = None,
) -> pd.DataFrame:
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


def make_amount_signed(
    df: pd.DataFrame,
    amount_col: str = "amount_num",
    type_col: str = "type_norm",
    out_col: str = "amount_signed",
) -> pd.DataFrame:
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


def report_mapped_unmapped(df: pd.DataFrame) -> None:
    """Print mapped pairs and unmapped raw values (to extend dictionaries)."""
    if not DEBUG_UNMAPPED:
        return

    def _diff(raw_col: str, norm_col: str, label: str):
        if raw_col in df.columns and norm_col in df.columns:
            raw = df[raw_col].astype("string").str.lower().str.strip()
            norm = df[norm_col].astype("string").str.lower().str.strip()
            mapped = pd.DataFrame({raw_col: raw, norm_col: norm})
            mapped = mapped[(mapped[raw_col] != mapped[norm_col]) & mapped[raw_col].ne("")]
            if not mapped.empty:
                print(f"\n[MAPPED] {label} variants (unique pairs):")
                print(mapped.drop_duplicates().head(40).to_string(index=False))
            same = raw[raw.eq(norm) & raw.ne("")]
            if not same.empty:
                print(f"\n[UNMAPPED] {label} values (top 20):")
                print(same.value_counts().head(20))

    _diff("category", "category_norm", "category")
    _diff("payment_method", "payment_method_norm", "payment_method")
    _diff("source", "source_norm", "source")

# -------------------------------------------------------------------
# Validation, buckets, enforcement
# -------------------------------------------------------------------

REQUIRED_COLS = {"date", "type", "amount"}

def validate_ledger(df: pd.DataFrame) -> None:
    """Check required cols, missing values, and duplicates."""
    missing = REQUIRED_COLS - set(map(str.lower, df.columns))
    if missing:
        raise ValueError(f"Ledger missing required columns: {sorted(missing)}")
    print("[VALIDATION] Missing values per column:\n", df.isna().sum())
    dups = df.duplicated().sum()
    if dups:
        print(f"[VALIDATION] Warning: {dups} duplicate rows detected.")

def apply_bucket(df: pd.DataFrame, cat_col: str = "category_norm", out_col: str = "bucket") -> pd.DataFrame:
    """Map category_norm/type_norm into a coarse bucket: needs/wants/savings/taxes/income."""
    out = df.copy()
    if cat_col in out.columns:
        out[out_col] = out[cat_col].map(lambda v: BUCKET_MAP.get(str(v), "wants"))
    if "type_norm" in out.columns:
        out.loc[out["type_norm"].eq("income"), out_col] = "income"
    return out

def _collect_violations(df: pd.DataFrame) -> Tuple[List[str], pd.DataFrame]:
    """Return (messages, suggestions_df) about schema issues and typo suggestions."""
    msgs: List[str] = []
    suggestions_rows: List[Tuple[str, str, str]] = []  # (column, bad_value, suggestion)

    # Amount must be numeric
    if "amount_num" in df.columns:
        bad_amt = df[pd.to_numeric(df["amount_num"], errors="coerce").isna()]
        if not bad_amt.empty:
            msgs.append(f"- {len(bad_amt)} rows have non-numeric amount_num")

    # Date must parse
    if "date_dt" in df.columns:
        bad_date = df[df["date_dt"].isna()]
        if not bad_date.empty:
            msgs.append(f"- {len(bad_date)} rows have invalid dates")

    # Type must be allowed
    if "type_norm" in df.columns:
        bad_type = df[~df["type_norm"].isin(TYPE_ALLOWED)]
        if not bad_type.empty:
            msgs.append(f"- {len(bad_type)} rows have invalid type_norm (allowed: {sorted(TYPE_ALLOWED)})")
            for v in bad_type["type_norm"].dropna().unique():
                suggestion = _closest(str(v), TYPE_ALLOWED, n=1)
                if suggestion:
                    suggestions_rows.append(("type_norm", str(v), suggestion[0]))

    # Category must be canonical
    if "category_norm" in df.columns:
        bad_cat = df[~df["category_norm"].isin(CATEGORY_ALLOWED)]
        if not bad_cat.empty:
            msgs.append(f"- {len(bad_cat)} rows have invalid category_norm (allowed: {sorted(CATEGORY_ALLOWED)})")
            for v in bad_cat["category_norm"].dropna().unique():
                suggestion = _closest(str(v), CATEGORY_ALLOWED, n=1)
                if suggestion:
                    suggestions_rows.append(("category_norm", str(v), suggestion[0]))

    # Payment method must be canonical if present
    if "payment_method_norm" in df.columns:
        bad_pm = df[~df["payment_method_norm"].isin(PAYMENT_ALLOWED)]
        if not bad_pm.empty:
            msgs.append(f"- {len(bad_pm)} rows have invalid payment_method_norm (allowed: {sorted(PAYMENT_ALLOWED)})")
            for v in bad_pm["payment_method_norm"].dropna().unique():
                suggestion = _closest(str(v), PAYMENT_ALLOWED, n=1)
                if suggestion:
                    suggestions_rows.append(("payment_method_norm", str(v), suggestion[0]))

    suggestions = pd.DataFrame(suggestions_rows, columns=["column", "value", "suggestion"]).drop_duplicates()
    return msgs, suggestions

def enforce_schema(df: pd.DataFrame, strict: bool = False) -> pd.DataFrame:
    """
    Enforce schema rules:
      - amount_num numeric
      - date_dt valid
      - type_norm ∈ {'income','expense'}
      - category_norm ∈ canonical set
      - payment_method_norm ∈ canonical set
    Prints warnings + suggestions; if strict=True, raises on violations.
    """
    msgs, suggestions = _collect_violations(df)
    if msgs:
        print("\n[SCHEMA] Issues detected:")
        for m in msgs:
            print(m)
    if not suggestions.empty:
        print("\n[SUGGEST] Possible corrections (closest matches):")
        print(suggestions.to_string(index=False))

    if strict and (msgs or not suggestions.empty):
        raise ValueError("Schema violations found. Fix inputs or extend mappings.")
    return df

# -------------------------------------------------------------------
# Orchestrator
# -------------------------------------------------------------------

def clean_ledger(df: pd.DataFrame, strict: bool = False) -> pd.DataFrame:
    """Run full cleaning pipeline, return ready-to-analyze frame."""
    # 1) normalize headers, validate minimal shape
    df1 = normalize_columns(df)
    validate_ledger(df1)

    # 2) non-destructive text normalization (adds *_norm for text cols, fixes typos in known fields)
    df2 = lowercase_strings(df1, make_norm_cols=True)

    # 3) type normalization and numeric/date coercions
    df3 = normalize_type(df2, col="type", out_col="type_norm")
    df4 = coerce_amount(df3, col="amount", out_col="amount_num")
    df5 = coerce_date(df4, col="date", out_col="date_dt")

    # 4) posted flag
    if "posted" in df5.columns:
        df5 = coerce_bool(df5, col="posted", out_col="posted_bool")

    # 5) category & payment canonicalization to stable buckets (overwrite *_norm with canonical values)
    if "category" in df5.columns:
        df5 = normalize_simple(df5, "category", CATEGORY_MAP, "category_norm")
    if "payment_method" in df5.columns:
        df5 = normalize_simple(df5, "payment_method", PAYMENT_MAP, "payment_method_norm")
    df5 = fill_unknowns(df5)

    # 6) signed amounts
    df6 = make_amount_signed(df5, amount_col="amount_num", type_col="type_norm", out_col="amount_signed")

    # 7) Needs/Wants/Savings/Taxes bucket
    df7 = apply_bucket(df6)

    # 8) mapped/unmapped reports and schema enforcement
    report_mapped_unmapped(df7)
    df7 = enforce_schema(df7, strict=strict)

    return df7
