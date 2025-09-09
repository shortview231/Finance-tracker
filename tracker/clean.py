# tracker/clean.py
# Unified cleaning utilities for Finance-Tracker
# - Header normalization + aliasing (from mappings.py)
# - Text cleanup + typo fixes (from mappings.py)
# - Type/category/payment canonicalization (schema-driven)
# - Date/amount coercion
# - Posted -> boolean (robust even if raw missing)
# - Signed amounts (+ income, - expense)
# - Needs/Wants/Savings/Taxes bucket
# - Validation + closest-match suggestions
# - Final column ordering (CLEAN_HEADERS first, extras preserved)

from __future__ import annotations

import re
import difflib
from datetime import datetime
from typing import Optional, Iterable, Mapping, Dict, List, Tuple, Any

import numpy as np
import pandas as pd

# === central schema + mappings ===
from .schema import (
    RAW_REQUIRED,
    RAW_OPTIONAL_DEFAULTS,
    VALUE_DOMAINS,
    CLEAN_HEADERS,
)
from .mappings import (
    HEADER_ALIASES,
    TYPE_MAP,
    CATEGORY_MAP,
    PAYMENT_METHOD_MAP,
    SPELLING_FIXES,
    BUCKET_RULES,
)

__all__ = [
    "normalize_columns",
    "apply_header_aliases",
    "ensure_required_optional",
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
    "clean_doordash_data",
]

# -------------------------------------------------------------------
# Config / constants
# -------------------------------------------------------------------

TEXT_DTYPES = ("object", "string")

# Keep debug quiet by default
DEBUG_DATES = False
DEBUG_UNMAPPED = False

TYPE_ALLOWED = VALUE_DOMAINS.get("type", {"income", "expense"})

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def _closest(value: str, candidates: Iterable[str], n: int = 1) -> List[str]:
    """Return up to n close matches from candidates."""
    if not value:
        return []
    return difflib.get_close_matches(value, list(candidates), n=n, cutoff=0.6)

def _canon_map_from_aliases(mapping: Mapping[str, str]) -> Dict[str, str]:
    """
    Build a normalized alias map keyed by snake_case (lower, spaces->underscore) to the canonical name.
    E.g., 'Payment Method' -> 'payment_method'
    """
    canon: dict[str, str] = {}
    for k, v in mapping.items():
        kk = str(k).strip().lower().replace(" ", "_")
        canon[kk] = v
    return canon

# -------------------------------------------------------------------
# Core normalizers
# -------------------------------------------------------------------

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardize header names to snake_case (trim, lowercase, spaces -> _),
    then coalesce any duplicate column names that result from normalization.
    The first occurrence wins, later duplicates fill gaps (NaN/blank) in the first.
    """
    out = df.copy()
    norm_cols = (
        pd.Index(out.columns)
        .str.strip()
        .str.lower()
        .str.replace(r"\s+", "_", regex=True)
    )
    out.columns = norm_cols

    # If no duplicates after normalization, we are done
    counts = out.columns.value_counts()
    dup_names = [c for c, n in counts.items() if n > 1]
    if not dup_names:
        return out

    def _is_blank_like(series: pd.Series) -> pd.Series:
        """Blank for strings is empty or whitespace; for others only NaN."""
        if pd.api.types.is_string_dtype(series) or series.dtype.name in ("object", "string"):
            s = series.astype("string")
            return s.isna() | s.str.strip().eq("")
        return series.isna()

    # Build a new set of columns, preserving first-seen order
    new_cols: dict[str, pd.Series] = {}
    seen: set[str] = set()

    for idx, col_name in enumerate(out.columns):
        if col_name in seen:
            # already handled via coalescing
            continue

        # collect all positions for this normalized name
        positions = [j for j, c in enumerate(out.columns) if c == col_name]
        base = out.iloc[:, positions[0]].copy()

        # coalesce later duplicates into base
        for j in positions[1:]:
            cand = out.iloc[:, j]
            need = _is_blank_like(base)
            # if both string-like, also treat cand blanks as not useful
            if pd.api.types.is_string_dtype(cand) or cand.dtype.name in ("object", "string"):
                cand_use = cand.where(~_is_blank_like(cand), pd.NA)
            else:
                cand_use = cand
            base = base.where(~need, cand_use)

        new_cols[col_name] = base
        seen.add(col_name)

    # Recreate DataFrame with coalesced, de-duplicated columns in first-seen order
    ordered_names = []
    seen = set()
    for c in out.columns:
        if c not in seen:
            ordered_names.append(c)
            seen.add(c)

    out = pd.DataFrame({c: new_cols[c] for c in ordered_names})
    return out


def apply_header_aliases(df: pd.DataFrame) -> pd.DataFrame:
    """Apply HEADER_ALIASES after snake_casing so raw sheet headers map to our canonical raw names."""
    out = df.copy()
    alias_norm = _canon_map_from_aliases(HEADER_ALIASES)
    out = out.rename(columns=alias_norm)
    return out


def ensure_required_optional(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure required columns exist; create missing optional columns with defaults."""
    out = df.copy()
    for col in RAW_REQUIRED + list(RAW_OPTIONAL_DEFAULTS):
        if col not in out.columns:
            out[col] = RAW_OPTIONAL_DEFAULTS.get(col, "")
    return out


def lowercase_strings(df: pd.DataFrame, make_norm_cols: bool = False) -> pd.DataFrame:
    """
    Normalize text columns: lowercase, strip, collapse spaces, fix common typos from SPELLING_FIXES.
    If make_norm_cols=True, also create *_norm for ALL text columns (safe defaults).
    Robust even if a column is non-string or if prior steps created odd dtypes.
    """
    out = df.copy()

    def norm_series(s: pd.Series) -> pd.Series:
        return (
            s.astype("string", copy=False)
             .str.lower()
             .str.strip()
             .str.replace(r"\s+", " ", regex=True)
             .replace(SPELLING_FIXES)
        )

    # targeted normals for common semantic columns
    for col in ("source", "category", "description", "payment_method", "name"):
        if col in out.columns:
            out[f"{col}_norm"] = norm_series(out[col])

    if make_norm_cols:
        for c in list(out.columns):
            # guard: if duplicate-name shenanigans ever returned a DataFrame, take first col
            col_obj = out[c]
            if isinstance(col_obj, pd.DataFrame):
                col_obj = col_obj.iloc[:, 0]

            dtype_name = getattr(col_obj.dtype, "name", "")
            if dtype_name in TEXT_DTYPES and not c.endswith("_norm"):
                norm_c = f"{c}_norm"
                if norm_c not in out.columns:
                    out[norm_c] = (
                        col_obj.astype("string", copy=False)
                               .str.lower()
                               .str.strip()
                               .str.replace(r"\s+", " ", regex=True)
                    )
    return out

def sanitize_column_names_for_bq(df: pd.DataFrame) -> pd.DataFrame:
    """
    Make column names BigQuery-safe:
    - keep only letters, numbers, underscores
    - collapse runs of invalid chars to a single underscore
    - strip leading/trailing underscores
    - ensure not empty
    """
    out = df.copy()
    new_cols = (
        pd.Index(out.columns)
        .str.replace(r"[^A-Za-z0-9_]", "_", regex=True)
        .str.replace(r"_+", "_", regex=True)
        .str.strip("_")
        .where(lambda s: s.ne(""), other="col")  # guard against empty
    )
    out.columns = new_cols
    return out


def normalize_type(df: pd.DataFrame, col: str = "type", out_col: Optional[str] = None) -> pd.DataFrame:
    """Normalize type column to 'income' or 'expense' in a new column (default: type_norm)."""
    out = df.copy()
    out_col = out_col or f"{col}_norm"

    # Flatten TYPE_MAP keys to handle many variants
    flat_type_map: Dict[str, str] = {}
    for k, v in TYPE_MAP.items():
        flat_type_map[str(k).strip().lower()] = v

    def norm(val):
        if pd.isna(val):
            return None
        v = str(val).strip().lower()
        if v in flat_type_map:
            return flat_type_map[v]
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

def normalize_simple(
    df: pd.DataFrame,
    col: str,
    mapping: Optional[Mapping[str, str]] = None,
    out_col: Optional[str] = None,
) -> pd.DataFrame:
    """Lowercase/trim a text column and optionally map common variants/typos to canonical values."""
    out = df.copy()
    out_col = out_col or f"{col}_norm"
    s = out[col].astype("string").str.strip().str.replace(r"\s+", " ", regex=True).str.lower()

    if mapping:
        # flatten mapping (already flat in mappings.py, but we normalize keys anyway)
        flat: Dict[str, str] = {}
        for k, v in mapping.items():
            flat[str(k).strip().lower()] = v
        s = s.map(lambda v: flat.get(v, v))

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
    """Apply +/- sign to amounts depending on type_norm."""
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
    """Print mapped pairs and truly unmapped raw values. Ignores already-canonical values."""
    if not DEBUG_UNMAPPED:
        return

    allowed_cats = set(CATEGORY_MAP.values()) | {"misc"}
    allowed_pm = set(PAYMENT_METHOD_MAP.values())

    def _diff(raw_col: str, norm_col: str, label: str, allowed: set | None = None):
        if raw_col in df.columns and norm_col in df.columns:
            raw = df[raw_col].astype("string").str.lower().str.strip()
            norm = df[norm_col].astype("string").str.lower().str.strip()

            mapped = pd.DataFrame({raw_col: raw, norm_col: norm})
            mapped = mapped[(mapped[raw_col] != mapped[norm_col]) & mapped[raw_col].ne("")]
            if not mapped.empty:
                print(f"\n[MAPPED] {label} variants (unique pairs):")
                print(mapped.drop_duplicates().head(40).to_string(index=False))

            if allowed is not None:
                same = raw[(raw.eq(norm)) & raw.ne("") & (~raw.isin(allowed))]
            else:
                same = raw[(raw.eq(norm)) & raw.ne("")]
            if not same.empty:
                print(f"\n[UNMAPPED] {label} values (top 20):")
                print(same.value_counts().head(20))

    _diff("category", "category_norm", "category", allowed_cats)
    _diff("payment_method", "payment_method_norm", "payment_method", allowed_pm)
    _diff("source", "source_norm", "source", None)

# -------------------------------------------------------------------
# Validation, buckets, enforcement
# -------------------------------------------------------------------

REQUIRED_COLS = set(RAW_REQUIRED)

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
        out[out_col] = out[cat_col].map(lambda v: BUCKET_RULES.get(str(v), "wants"))
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
        allowed_cats = set(CATEGORY_MAP.values()) | {"misc"}
        bad_cat = df[~df["category_norm"].isin(allowed_cats)]
        if not bad_cat.empty:
            msgs.append(f"- {len(bad_cat)} rows have invalid category_norm (allowed: {sorted(allowed_cats)})")
            for v in bad_cat["category_norm"].dropna().unique():
                suggestion = _closest(str(v), allowed_cats, n=1)
                if suggestion:
                    suggestions_rows.append(("category_norm", str(v), suggestion[0]))

    # Payment method must be canonical if present
    if "payment_method_norm" in df.columns:
        allowed_pm = set(PAYMENT_METHOD_MAP.values())
        bad_pm = df[~df["payment_method_norm"].isin(allowed_pm)]
        if not bad_pm.empty:
            msgs.append(f"- {len(bad_pm)} rows have invalid payment_method_norm (allowed: {sorted(allowed_pm)})")
            for v in bad_pm["payment_method_norm"].dropna().unique():
                suggestion = _closest(str(v), allowed_pm, n=1)
                if suggestion:
                    suggestions_rows.append(("payment_method_norm", str(v), suggestion[0]))

    suggestions = pd.DataFrame(suggestions_rows, columns=["column", "value", "suggestion"]).drop_duplicates()
    return msgs, suggestions

def enforce_schema(df: pd.DataFrame, strict: bool = False) -> pd.DataFrame:
    """
    Enforce schema rules:
      - amount_num numeric
      - date_dt valid
      - type_norm in {'income','expense'}
      - category_norm in canonical set
      - payment_method_norm in canonical set
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
def clean_doordash_data(df_doordash: pd.DataFrame, df_goals: pd.DataFrame) -> pd.DataFrame:
    """
    Cleans and processes DoorDash data and calculates totals against a cap.
    """
    # Extract the income cap from the goals DataFrame
    income_cap_series = df_goals[df_goals['metric'] == 'DoorDash Income Cap']['value']
    if not income_cap_series.empty:
        income_cap = pd.to_numeric(income_cap_series.iloc[0], errors='coerce')
    else:
        income_cap = 0  # Default cap if not found

    # Ensure columns are in the correct format for calculations
    df_doordash['Date'] = pd.to_datetime(df_doordash.get('Date'), errors='coerce')
    df_doordash['Amount'] = pd.to_numeric(df_doordash.get('Amount'), errors='coerce')

    # Calculate daily totals, running balance, and progress to cap
    if 'Date' in df_doordash.columns and 'Amount' in df_doordash.columns:
        df_doordash['daily_total'] = df_doordash.groupby('Date')['Amount'].transform('sum')
        df_doordash['running_balance'] = df_doordash['Amount'].cumsum()
        df_doordash['progress_to_cap'] = income_cap - df_doordash['running_balance']

    # Add a 'category' column for dashboard filtering
    df_doordash['category'] = 'doordash'

    # Rename columns to match the main ledger schema
    df_doordash = df_doordash.rename(columns={
        'Date': 'date',
        'Amount': 'amount'
    })

    return df_doordash

def clean_ledger(df: pd.DataFrame, strict: bool = False) -> pd.DataFrame:
    """Run full cleaning pipeline, return ready-to-analyze frame."""
    # 1) normalize headers, alias, ensure shape
    df1 = normalize_columns(df)
    df1 = apply_header_aliases(df1)
    df1 = ensure_required_optional(df1)
    validate_ledger(df1)

    # 2) non-destructive text normalization (adds *_norm for text cols, fixes typos)
    df2 = lowercase_strings(df1, make_norm_cols=True)

    # 3) type normalization and numeric/date coercions
    df3 = normalize_type(df2, col="type", out_col="type_norm")
    df4 = coerce_amount(df3, col="amount", out_col="amount_num")
    df5 = coerce_date(df4, col="date", out_col="date_dt")

    # 4) posted flag (robust if raw missing)
    if "posted" in df5.columns:
        df5 = coerce_bool(df5, col="posted", out_col="posted_bool")

    # 5) category and payment canonicalization
    if "category" in df5.columns:
        df5 = normalize_simple(df5, "category", CATEGORY_MAP, "category_norm")
    if "payment_method" in df5.columns:
        df5 = normalize_simple(df5, "payment_method", PAYMENT_METHOD_MAP, "payment_method_norm")
    df5 = fill_unknowns(df5)

    # 5a) ensure name fields are not blank or NaN
    if "name" in df5.columns:
        df5["name"] = df5["name"].astype("string").fillna("N/A")
        df5.loc[df5["name"].str.strip().eq(""), "name"] = "N/A"
    if "name_norm" in df5.columns:
        df5["name_norm"] = df5["name_norm"].astype("string").fillna("N/A")
        df5.loc[df5["name_norm"].str.strip().eq(""), "name_norm"] = "N/A"

    # 5b) force type_norm for inherently income categories
    if "category_norm" in df5.columns:
        income_cats = {"doordash", "disability"}
        df5.loc[df5["category_norm"].isin(income_cats), "type_norm"] = "income"

    # 6) signed amounts
    df6 = make_amount_signed(df5, amount_col="amount_num", type_col="type_norm", out_col="amount_signed")

    # 7) bucket
    df7 = apply_bucket(df6)

    # 8) finalize posted column
    if "posted_bool" in df7.columns:
        df7["posted"] = df7["posted_bool"].fillna(True)
    elif "posted" not in df7.columns:
        df7["posted"] = True

    # 9) reports and schema enforcement
    report_mapped_unmapped(df7)
    df7 = enforce_schema(df7, strict=strict)

    # 10) final ordering
    ordered = [c for c in CLEAN_HEADERS if c in df7.columns]
    rest = [c for c in df7.columns if c not in ordered]
    return df7[ordered + rest]
