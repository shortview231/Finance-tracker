# tracker/clean.py
import pandas as pd
import numpy as np

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
