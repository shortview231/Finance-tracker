# tracker/io.py
from __future__ import annotations

from pathlib import Path
from typing import Optional, Dict, Any, List, Union
import pandas as pd

# Google API imports
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2 import service_account

# --- config loader: tomllib on 3.11+, tomli fallback on 3.10 ---
try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    import tomli as tomllib  # Python 3.10 fallback


# =========================
# Config helpers
# =========================
def _load_config() -> Dict[str, Any]:
    """
    Load config.toml from project root.
    """
    cfg_path = Path("config.toml")
    if not cfg_path.exists():
        raise FileNotFoundError(
            "config.toml not found.\n"
            "Add one with e.g.\n"
            "[google]\n"
            "spreadsheet_id = \"...\"\n"
        )
    with cfg_path.open("rb") as f:
        return tomllib.load(f)


def _get_google_sheet_id(cfg: Dict[str, Any]) -> str:
    ssid = (
        cfg.get("google", {}).get("spreadsheet_id")
        or cfg.get("sheets", {}).get("spreadsheet_id")
    )
    if not ssid:
        raise ValueError("Missing spreadsheet_id in config.toml (expected under [google]).")
    return ssid


def _get_tab_range(cfg: Dict[str, Any], tab_name: str) -> str:
    """
    Resolve a tab range.
    Checks [ranges] case-insensitively, else defaults to "{Tab}!A:Z".
    """
    ranges = cfg.get("ranges", {}) or {}
    # exact
    if tab_name in ranges:
        return ranges[tab_name]
    # case-insensitive fallback
    lower_map = {k.lower(): v for k, v in ranges.items()}
    if tab_name.lower() in lower_map:
        return lower_map[tab_name.lower()]
    return f"{tab_name}!A:Z"


# =========================
# Google Sheets: auth / service
# =========================
READONLY_SCOPE = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
WRITE_SCOPE    = ["https://www.googleapis.com/auth/spreadsheets"]


def _get_credentials(scopes: List[str]) -> service_account.Credentials:
    """
    Build service account credentials for the given scopes.
    Expects config.toml -> [google].token_path to point at a SERVICE ACCOUNT JSON key.
    """
    cfg = _load_config()
    token_path = Path(cfg.get("google", {}).get("token_path", ""))

    if not token_path:
        raise ValueError("Missing [google].token_path in config.toml (service account key path).")
    if not token_path.exists():
        raise FileNotFoundError(f"Google credentials JSON not found: {token_path}")

    creds = service_account.Credentials.from_service_account_file(
        str(token_path),
        scopes=scopes,
    )
    return creds


def _get_sheets_service(scopes: Optional[List[str]] = None):
    """
    Build the Sheets API service with the given scopes.
    """
    SCOPES = scopes or READONLY_SCOPE
    creds = _get_credentials(SCOPES)
    service = build("sheets", "v4", credentials=creds)
    return service


def _ensure_sheet_tab(service, spreadsheet_id: str, tab_name: str) -> None:
    """
    Ensure a tab with `tab_name` exists in the spreadsheet. If missing, create it.
    """
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    titles = [s["properties"]["title"] for s in meta.get("sheets", [])]
    if tab_name not in titles:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
        ).execute()


# =========================
# Public API used by tracker_api.py
# =========================
def read_sheet_to_df(
    sheet_name: str,
    spreadsheet_id: Optional[str] = None,
) -> pd.DataFrame:
    """
    Reads a single Sheet tab into a DataFrame.
    Uses [ranges] overrides if present in config.
    """
    cfg = _load_config()
    ssid = spreadsheet_id or _get_google_sheet_id(cfg)
    range_str = _get_tab_range(cfg, sheet_name)

    service = _get_sheets_service(scopes=READONLY_SCOPE)
    try:
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=ssid, range=range_str)
            .execute()
        )
    except HttpError as e:
        print(f"⚠️ Could not read sheet '{sheet_name}': {e}")
        return pd.DataFrame()

    values: List[List[str]] = result.get("values", [])
    if not values:
        return pd.DataFrame()

    header = values[0]
    rows = values[1:]
    # pad rows to header length
    fixed_rows: List[List[str]] = [r + [""] * (len(header) - len(r)) for r in rows]
    return pd.DataFrame(fixed_rows, columns=header)


def read_sheets_to_dfs(
    tab_names: List[str],
    spreadsheet_id: Optional[str] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Reads a list of Sheet tabs into a dictionary of DataFrames.
    """
    dfs: Dict[str, pd.DataFrame] = {}
    for name in tab_names:
        dfs[name] = read_sheet_to_df(name, spreadsheet_id)
    return dfs


def write_df_to_sheet(
    df: pd.DataFrame,
    spreadsheet_id: Optional[str] = None,
    tab_name: str = "Ledger_CLEAN",
    clear_before_write: bool = True,
    value_input_option: str = "USER_ENTERED",
) -> None:
    """
    Write a DataFrame to a Sheet tab. Overwrites by default.
    - Dates are formatted as YYYY-MM-DD
    - NaNs become empty strings
    """
    cfg = _load_config()
    ssid = spreadsheet_id or _get_google_sheet_id(cfg)

    service = _get_sheets_service(scopes=WRITE_SCOPE)
    _ensure_sheet_tab(service, ssid, tab_name)

    df_out = df.copy()

    # Format dates and stringify others
    for c in df_out.columns:
        if pd.api.types.is_datetime64_any_dtype(df_out[c]):
            df_out[c] = pd.to_datetime(df_out[c], errors="coerce").dt.strftime("%Y-%m-%d")
        else:
            # Ensure clean strings for Sheets; drop "nan"
            ser = df_out[c]
            # If it's numeric, leave it as-is to preserve numbers in Sheets
            if pd.api.types.is_numeric_dtype(ser):
                continue
            df_out[c] = ser.astype(str).replace("nan", "")

    values: List[List[Union[str, float, int]]] = [df_out.columns.tolist()] + df_out.values.tolist()
    start_range = f"{tab_name}!A1"

    try:
        if clear_before_write:
            service.spreadsheets().values().clear(
                spreadsheetId=ssid,
                range=f"{tab_name}!A:ZZ",
                body={}
            ).execute()

        service.spreadsheets().values().update(
            spreadsheetId=ssid,
            range=start_range,
            valueInputOption=value_input_option,
            body={"values": values},
        ).execute()
        print(f"✅ Successfully wrote DataFrame to sheet: {tab_name}")
    except HttpError as e:
        print(f"❌ Sheets write failed for '{tab_name}': {e}")
