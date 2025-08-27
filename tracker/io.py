# tracker/io.py
from __future__ import annotations

from pathlib import Path
from typing import Optional, Dict, Any, List
import pandas as pd

# --- config loader: tomllib on 3.11+, tomli fallback on 3.10 ---
try:
    import tomllib  # Python 3.11+  # type: ignore[import]
except ModuleNotFoundError:
    import tomli as tomllib  # Python 3.10 fallback


# =========================
# Config helpers
# =========================
def _load_config() -> Dict[str, Any]:
    cfg_path = Path("config.toml")
    if not cfg_path.exists():
        raise FileNotFoundError(
            "config.toml not found.\n"
            "Add one with e.g.\n"
            "[google]\n"
            "spreadsheet_id = \"...\"\n"
            "calendar_id = \"primary\"\n"
            "timezone = \"America/Chicago\"\n\n"
            "[ranges]\n"
            "ledger = \"ledger!A:G\"\n"
        )
    with cfg_path.open("rb") as f:
        return tomllib.load(f)


def _get_google_sheet_id(cfg: Dict[str, Any]) -> str:
    # Prefer your [google] block; fall back to older [sheets]
    ssid = (
        cfg.get("google", {}).get("spreadsheet_id")
        or cfg.get("sheets", {}).get("spreadsheet_id")
    )
    if not ssid:
        raise ValueError("Missing spreadsheet_id (expected under [google] or [sheets]).")
    return ssid


def _get_ledger_range(cfg: Dict[str, Any]) -> str:
    # If [ranges].ledger exists, use it; else build from [sheets].ledger_tab (default: 'Ledger')
    rng = cfg.get("ranges", {}).get("ledger")
    if rng:
        return rng
    tab = cfg.get("sheets", {}).get("ledger_tab", "Ledger")
    return f"{tab}!A:Z"


# =========================
# Google APIs (Sheets)
# =========================
def _get_sheets_service(scopes: Optional[List[str]] = None):
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    SCOPES = scopes or ["https://www.googleapis.com/auth/spreadsheets.readonly"]

    creds = None
    token_path = Path("token.json")
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # credentials.json must exist in repo root (keep it in .gitignore)
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())

    return build("sheets", "v4", credentials=creds)


# =========================
# Public API used by tracker_api.py
# =========================
def read_ledger_from_sheets(
    spreadsheet_id: Optional[str] = None,
    tab_name: Optional[str] = None,   # ignored if [ranges].ledger is set
    col_range: Optional[str] = None,  # ignored if [ranges].ledger is set
) -> pd.DataFrame:
    """
    Read the Ledger into a DataFrame.

    Configuration styles supported:
    - Your style:
        [google]
        spreadsheet_id = "..."
        [ranges]
        ledger = "ledger!A:G"

    - Older style:
        [sheets]
        spreadsheet_id = "..."
        ledger_tab = "Ledger"
    """
    cfg = _load_config()
    ssid = spreadsheet_id or _get_google_sheet_id(cfg)

    # Determine range to fetch
    if cfg.get("ranges", {}).get("ledger"):
        range_str = cfg["ranges"]["ledger"]
    else:
        tab = tab_name or cfg.get("sheets", {}).get("ledger_tab", "Ledger")
        cr = col_range or "A:Z"
        range_str = f"{tab}!{cr}"

    service = _get_sheets_service()
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=ssid, range=range_str)
        .execute()
    )
    values: List[List[str]] = result.get("values", [])
    if not values:
        return pd.DataFrame()

    header = values[0]
    rows = values[1:]
    return pd.DataFrame(rows, columns=header)


# =========================
# Optional: write helper (for later)
# =========================
def write_df_to_sheet(
    df: pd.DataFrame,
    spreadsheet_id: Optional[str] = None,
    tab_name: str = "Ledger_CLEAN",
    clear_before_write: bool = True,
):
    """
    Write a DataFrame to a Sheet tab (overwrites by default).
    Requires full Sheets scope (not readonly).
    """
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    cfg = _load_config()
    ssid = spreadsheet_id or _get_google_sheet_id(cfg)

    # Need write scope
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = None
    token_path = Path("token.json")
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())

    service = build("sheets", "v4", credentials=creds)

    # Ensure header + rows are strings
    values = [list(map(str, df.columns.tolist()))] + df.astype(str).values.tolist()
    range_name = f"{tab_name}!A1"

    if clear_before_write:
        # Clear the whole tab first
        service.spreadsheets().values().clear(
            spreadsheetId=ssid,
            range=f"{tab_name}!A:ZZ",
            body={}
        ).execute()

    service.spreadsheets().values().update(
        spreadsheetId=ssid,
        range=range_name,
        valueInputOption="RAW",
        body={"values": values},
    ).execute()
