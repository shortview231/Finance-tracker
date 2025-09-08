# tracker/clean.py
# Unified cleaning utilities for Finance-Tracker
# - Header normalization + aliasing (from mappings.py)
# - Text cleanup + typo fixes (from mappings.py)
# - Type/category/payment canonicalization (schema-driven)
# - Date/amount coercion
# - Posted -> boolean (robust even if raw missing)
# - Signed amounts (+ income, − expense)
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
    "clean_doordash_data",
    "clean_ledger",
]

# =========================
# 1) Column header normalization
# =========================
def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardize column headers: lowercase, snake_case, no special chars.
    """
    out = df.copy()
    out.columns = (
        pd.Index(out.columns)
        .str.lower()
        .str.strip()
        .str.replace(r"[^a-z0-9_]+", "", regex=True)
        .str.replace(r"\s+", "_", regex=True)
    )
    return out


def apply_header_aliases(df: pd.DataFrame, aliases: Mapping[str, str]) -> pd.DataFrame:
    """
    Rename columns based on a mapping of common aliases -> canonical names.
    """
    return df.rename(columns=aliases)


# =========================
# 2) DataFrame shape/schema
# =========================
def ensure_required_optional(
    df: pd.DataFrame,
    required: Iterable[str],
    optional_defaults: Mapping[str, Any],
) -> pd.DataFrame:
    """
    Ensure all required columns are present; add optional columns with defaults if missing.
    """
    out = df.copy()
    missing = set(required) - set(out.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    for col, default in optional_defaults.items():
        if col not in out.columns:
            out[col] = default
    return out


# =========================
# 3) Value coercion / cleanup
# =========================
def lowercase_strings(df: pd.DataFrame) -> pd.DataFrame:
    """
    Lowercase and strip all string columns.
    """
    out = df.copy()
    for c in out.select_dtypes(include=["object", "string"]).columns:
        out[c] = out[c].astype(str).str.lower().str.strip()
    return out


def normalize_type(
    df: pd.DataFrame, col: str, out_col: str, type_map: Mapping[str, str]
) -> pd.DataFrame:
    """
    Normalize the 'type' column to canonical values (income/expense/transfer).
    """
    out = df.copy()
    if col in out.columns:
        out[out_col] = out[col].map(type_map)
    return out


def coerce_date(df: pd.DataFrame, col: str, out_col: str) -> pd.DataFrame:
    """
    Coerce a date column to datetime objects, handling various formats.
    """
    out = df.copy()
    if col in out.columns:
        out[out_col] = pd.to_datetime(out[col], errors="coerce")
    return out


def coerce_amount(df: pd.DataFrame, col: str, out_col: str) -> pd.DataFrame:
    """
    Coerce an amount column to numeric, handling $, commas, and parentheses for negatives.
    """
    out = df.copy()
    if col in out.columns:
        s = out[col].astype(str).str.strip()
        s = s.str.replace(r"[\$,]", "", regex=True)
        s = s.str.replace(r"\((.*)\)", r"-\1", regex=True)
        out[out_col] = pd.to_numeric(s, errors="coerce")
    return out


def normalize_simple(
    df: pd.DataFrame, col: str, mapping: Mapping[str, str], out_col: str
) -> pd.DataFrame:
    """
    Apply a simple key-value mapping to a column for canonicalization.
    """
    out = df.copy()
    if col in out.columns:
        out[out_col] = out[col].map(mapping).fillna(out[col])
    return out


def coerce_bool(df: pd.DataFrame, col: str, out_col: str) -> pd.DataFrame:
    """
    Coerce a column to boolean, mapping common string values.
    """
    out = df.copy()
    if col in out.columns:
        s = out[col].astype(str).str.strip().str.lower()
        true_vals = {"true", "t", "yes", "y", "1", "paid", "posted"}
        out[out_col] = s.isin(true_vals)
    return out


# =========================
# 4) Derived columns
# =========================
def make_amount_signed(
    df: pd.DataFrame, amount_col: str, type_col: str, out_col: str
) -> pd.DataFrame:
    """
    Create a signed amount column (+ for income, - for expense).
    """
    out = df.copy()
    if amount_col in out.columns and type_col in out.columns:
        sign = np.where(out[type_col] == "income", 1, -1)
        out[out_col] = out[amount_col].abs() * sign
    return out


def fill_unknowns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Fill NaNs in key normalized columns with placeholder values.
    """
    out = df.copy()
    if "category_norm" in out.columns:
        out["category_norm"] = out["category_norm"].fillna("misc")
    if "payment_method_norm" in out.columns:
        out["payment_method_norm"] = out["payment_method_norm"].fillna("unknown")
    return out


def apply_bucket(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply Needs/Wants/Savings/Taxes bucket based on category and type.
    """
    out = df.copy()

    def get_bucket(row):
        cat = row.get("category_norm", "")
        typ = row.get("type_norm", "")
        if typ == "income":
            return "income"
        for bucket, keywords in BUCKET_RULES.items():
            if cat in keywords:
                return bucket
        return "wants"  # Default for expenses

    if "category_norm" in out.columns and "type_norm" in out.columns:
        out["bucket"] = out.apply(get_bucket, axis=1)
    return out


# =========================
# 5) Validation / reporting
# =========================
def get_closest_match(
    value: str, allowed_values: Iterable[str], n: int = 1, cutoff: float = 0.6
) -> Optional[str]:
    """
    Find the closest match for a value from a list of allowed values.
    """
    matches = difflib.get_close_matches(value, allowed_values, n=n, cutoff=cutoff)
    return matches[0] if matches else None


def report_mapped_unmapped(
    df: pd.DataFrame, col: str, mapping: Mapping[str, str], title: str
) -> None:
    """
    Report on values in a column that were successfully mapped or remain unmapped.
    """
    s = df[col].dropna().unique()
    mapped = {k for k in s if k in mapping}
    unmapped = set(s) - mapped
    print(f"\n--- {title} ---")
    if mapped:
        print(f"  Mapped values ({len(mapped)}): {sorted(mapped)}")
    if unmapped:
        print(f"  Unmapped values ({len(unmapped)}):")
        for val in sorted(unmapped):
            suggestion = get_closest_match(val, mapping.keys())
            hint = f" (did you mean '{suggestion}'?)" if suggestion else ""
            print(f"    - {val}{hint}")


def validate_ledger(df: pd.DataFrame) -> None:
    """
    Run a series of validation checks on the cleaned ledger.
    """
    print("\n[VALIDATION] Missing values per column:")
    print(df.isna().sum())

    # Report on unmapped values for key columns
    print("\n[UNMAPPED] category values (top 20):")
    print(df["category"].value_counts().nlargest(20))
    print("\n[UNMAPPED] source values (top 20):")
    print(df["source"].value_counts().nlargest(20))

    # Schema validation against VALUE_DOMAINS
    print("\n[SCHEMA] Issues detected:")
    has_issues = False
    for col, allowed in VALUE_DOMAINS.items():
        if f"{col}_norm" in df.columns:
            invalid = df[~df[f"{col}_norm"].isin(allowed) & df[f"{col}_norm"].notna()]
            if not invalid.empty:
                has_issues = True
                print(f"- {len(invalid)} rows have invalid {col}_norm (allowed: {allowed})")
    if not has_issues:
        print("- No schema issues found.")


# =========================
# 6) Main cleaning pipeline
# =========================
def clean_doordash_data(df_doordash: pd.DataFrame, df_goals: pd.DataFrame) -> pd.DataFrame:
    """
    Cleans and processes the DoorDash DataFrame.
    """
    # Placeholder for DoorDash-specific cleaning logic
    return df_doordash

def clean_ledger(dfs: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    The main cleaning pipeline function.
    Takes a dictionary of DataFrames, merges them, and applies all cleaning steps.
    """
    # --- FIX STARTS HERE ---
    # Extract the main DataFrame from the dictionary.
    # It could be 'Ledger', 'merged', or the only one present.
    if "merged" in dfs:
        df = dfs["merged"].copy()
    elif "Ledger" in dfs:
        df = dfs["Ledger"].copy()
    elif len(dfs) == 1:
        df = list(dfs.values())[0].copy()
    else:
        # If we can't find a primary DataFrame, start with an empty one.
        # This prevents crashes if e.g. the 'Ledger' tab is missing.
        df = pd.DataFrame()

    if df.empty:
        print("⚠️ Warning: No data found to clean.")
        return df
    # --- FIX ENDS HERE ---

    # 1) headers
    df1 = normalize_columns(df)
    df1 = apply_header_aliases(df1, HEADER_ALIASES)
    df1 = ensure_required_optional(
        df1, required=RAW_REQUIRED, optional_defaults=RAW_OPTIONAL_DEFAULTS
    )

    # 2) global text cleanup (lowercase, strip, simple typo fixes)
    df2 = lowercase_strings(df1)
    for col in df2.select_dtypes(include=["object", "string"]).columns:
        df2[col] = df2[col].replace(SPELLING_FIXES)

    # 3) core value coercions
    df3 = normalize_type(df2, col="type", out_col="type_norm", type_map=TYPE_MAP)
    df4 = coerce_amount(df3, col="amount", out_col="amount_num")
    df5 = coerce_date(df4, col="date", out_col="date_dt")

    # 4) posted flag (robust if raw missing)
    if "posted" in df5.columns:
        df5 = coerce_bool(df5, col="posted", out_col="posted_bool")

    # 5) category & payment canonicalization (overwrite *_norm with canonical values)
    if "category" in df5.columns:
        df5 = normalize_simple(df5, "category", CATEGORY_MAP, "category_norm")
    if "payment_method" in df5.columns:
        df5 = normalize_simple(df5, "payment_method", PAYMENT_METHOD_MAP, "payment_method_norm")
    df5 = fill_unknowns(df5)

    # 6) signed amounts
    df6 = make_amount_signed(df5, amount_col="amount_num", type_col="type_norm", out_col="amount_signed")

    # 7) Needs/Wants/Savings/Taxes bucket
    df7 = apply_bucket(df6)

    # 8) finalize 'posted' column (prefer posted_bool if created). If missing entirely, assume True.
    if "posted_bool" in df7.columns:
        df7["posted"] = df7["posted_bool"].fillna(True)
    elif "posted" not in df7.columns:
        df7["posted"] = True # Assume posted if no column exists

    # 9) final column selection and ordering
    final_cols = [c for c in CLEAN_HEADERS if c in df7.columns]
    extra_cols = [c for c in df7.columns if c not in CLEAN_HEADERS]
    
    return df7[final_cols + extra_cols]

