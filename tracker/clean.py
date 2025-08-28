# tracker/clean.py
import pandas as pd
import numpy as np


def normalize_type(df: pd.DataFrame, col: str = "type", out_col: str | None = None) -> pd.DataFrame:
    """
    Normalize type column to 'income' or 'expense' in a new column (default: type_norm).
    Maps variants like 'in', 'pay', 'salary' to 'income', and 'exp', 'bill', 'debit' to 'expense'.
    """
    income_variants = {"income", "in", "pay", "salary", "deposit", "credit"}
    expense_variants = {"expense", "exp", "bill", "debit", "purchase", "withdrawal"}
    out = df.copy()
    if out_col is None:
        out_col = f"{col}_norm"
    def norm(val):
        if pd.isna(val):
            return None
        v = str(val).strip().lower()
        if v in income_variants:
            return "income"
        if v in expense_variants:
            return "expense"
        return v  # fallback: keep as-is
    out[out_col] = out[col].apply(norm)
    return out

TEXT_DTYPES = ("object", "string")

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

def lowercase_strings(df: pd.DataFrame, cols=None, make_norm_cols: bool = True) -> pd.DataFrame:
    """
    Trim spaces and lowercase selected text columns.

    - cols = None: auto-select all text-like columns
    - make_norm_cols = True: write results to new *_norm columns (non-destructive).
      If False, overwrite the original columns.
    """
    out = df.copy()

    # pick target columns
    if cols is None:
        target_cols = list(out.select_dtypes(include=TEXT_DTYPES).columns)
    else:
        target_cols = list(cols)

    for c in target_cols:
        # convert to pandas string dtype, normalize whitespace, lowercase
        s = (out[c].astype("string")
                     .str.strip()
                     .str.replace(r"\s+", " ", regex=True)
                     .str.lower())

        if make_norm_cols:
            out[f"{c}_norm"] = s
        else:
            out[c] = s

    return out

def coerce_date(df: pd.DataFrame, col: str = "date", out_col: str | None = None) -> pd.DataFrame:
    """
    Parse a date column into pandas datetime. Writes to a new column (default: date_dt).
    Leaves the original column untouched. Invalid parses become NaT.
    """
    out = df.copy()
    if out_col is None:
        out_col = f"{col}_dt"

    s = out[col].astype("string").str.strip()
    s = s.replace({"": None, "na": None, "n/a": None, "null": None}, regex=False)

    # Debug: print repr of raw date values for first 10 rows
    print("\n[DEBUG] Raw date values (repr) before parsing:")
    for i, val in enumerate(s.head(10)):
        print(f"Row {i}: {repr(val)}")

    import re
    from datetime import datetime
    current_year = str(datetime.now().year)
    def fix_date(val):
        if val is None or pd.isna(val):
            return val
        val = str(val).strip()
        # MM-DD-YYYY or YYYY-MM-DD (let pandas handle)
        if re.fullmatch(r"\d{1,2}-\d{1,2}-\d{4}", val) or re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", val):
            return val
        # MM-DD (add current year)
        if re.fullmatch(r"\d{1,2}-\d{1,2}", val):
            return f"{current_year}-{val}"
        return val
    s_fixed = s.apply(fix_date)

    # Debug: print repr of fixed date values for first 10 rows
    print("\n[DEBUG] Fixed date values (repr) after year-filling:")
    for i, val in enumerate(s_fixed.head(10)):
        print(f"Row {i}: {repr(val)}")

    out[out_col] = pd.to_datetime(s_fixed, errors="coerce")
    return out

    import re
    from datetime import datetime
    current_year = str(datetime.now().year)
    def fix_date(val):
        if val is None or pd.isna(val):
            return val
        val = val.strip()
        # MM-DD-YYYY or YYYY-MM-DD (let pandas handle)
        if re.fullmatch(r"\d{1,2}-\d{1,2}-\d{4}", val) or re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", val):
            return val
        # MM-DD (add current year)
        if re.fullmatch(r"\d{1,2}-\d{1,2}", val):
            return f"{current_year}-{val}"
        return val
    s = s.apply(fix_date)

    out[out_col] = pd.to_datetime(s, errors="coerce")
    return out

import re

def coerce_amount(df: pd.DataFrame, col: str = "amount", out_col: str | None = None) -> pd.DataFrame:
    """
    Clean and convert an amount column to float.
    - Removes $, commas, spaces.
    - Treats blanks, '---', 'na', 'n/a', 'null' as 0.
    - Converts (123.45) to -123.45.
    - Writes to a new column (default: amount_num).
    """
    out = df.copy()
    if out_col is None:
        out_col = f"{col}_num"

    s = out[col].astype("string").str.strip()
    # Handle blanks and common nulls
    s = s.replace({"": "0", "---": "0", "na": "0", "n/a": "0", "null": "0"}, regex=False)
    # Remove $ and commas, handle parentheses for negatives
    s = s.str.replace(r"[$,]", "", regex=True)
    s = s.str.replace(r"\(([^)]+)\)", r"-\1", regex=True)
    # Remove spaces
    s = s.str.replace(" ", "", regex=False)
    # Convert to float
    out[out_col] = pd.to_numeric(s, errors="coerce").fillna(0)
    return out