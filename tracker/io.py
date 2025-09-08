# tracker/io.py
from __future__ import annotations

from pathlib import Path
from typing import Optional, Dict, Any, List
import pandas as pd

# Google API imports (module-level so types are available everywhere)
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# --- config loader: tomllib on 3.11+, tomli fallback on 3.10 ---
try:
    import tomllib  # Python 3.11+  # type: ignore[import]
except ModuleNotFoundError:
    import tomli as tomllib  # Python 3.10 fallback


# =========================
# Config helpers
# =========================
def _load_config() -> Dict[str, Any]:
    """
    Load config.toml.
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


def _get_token_path(cfg: Dict[str, Any]) -> Path:
    return Path(cfg.get("google", {}).get("token_path", "token.json"))


def _get_tab_range(cfg: Dict[str, Any], tab_name: str) -> str:
    """
    If [ranges].tab_name is present, use it; else compose from tab_name + default range.
    """
    if cfg.get("ranges", {}).get(tab_name):
        return cfg["ranges"][tab_name]
    return f"{tab_name}!A:Z"


# =========================
# Google Sheets: auth / service
# =========================
READONLY_SCOPE = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
WRITE_SCOPE    = ["https://www.googleapis.com/auth/spreadsheets"]


def _get_credentials(scopes: List[str]) -> Credentials:
    """
    Retrieve credentials for the given scopes.
    """
    cfg = _load_config()
    token_path = _get_token_path(cfg)

    creds: Optional[Credentials] = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), scopes)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not Path("credentials.json").exists():
                raise FileNotFoundError(
                    "credentials.json not found. Download OAuth client credentials from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", scopes)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())

    return creds


def _get_sheets_service(scopes: Optional[List[str]] = None):
    """
    Build the Sheets API service with the given scopes.
    """
    SCOPES = scopes or READONLY_SCOPE
    creds = _get_credentials(SCOPES)
    return build("sheets", "v4", credentials=creds)


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
    """
    cfg = _load_config()
    ssid = spreadsheet_id or _get_google_sheet_id(cfg)
    range_str = _get_tab_range(cfg, sheet_name)

    service = _get_sheets_service(scopes=READONLY_SCOPE)
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
        try:
            dfs[name] = read_sheet_to_df(name, spreadsheet_id)
        except HttpError as e:
            print(f"⚠️ Could not read sheet '{name}': {e.error_details}")
            dfs[name] = pd.DataFrame()
    return dfs


def write_df_to_sheet(
    df: pd.DataFrame,
    spreadsheet_id: Optional[str] = None,
    tab_name: str = "Ledger_CLEAN",
    clear_before_write: bool = True,
    value_input_option: str = "USER_ENTERED",
) -> None:
    """
    Write a DataFrame to a Sheet tab (overwrites by default).
    """
    cfg = _load_config()
    ssid = spreadsheet_id or _get_google_sheet_id(cfg)

    service = _get_sheets_service(scopes=WRITE_SCOPE)
    _ensure_sheet_tab(service, ssid, tab_name)

    df_out = df.copy()
    for c in df_out.columns:
        if pd.api.types.is_datetime64_any_dtype(df_out[c]):
            df_out[c] = pd.to_datetime(df_out[c], errors="coerce").dt.strftime("%Y-%m-%d")
        else:
            df_out[c] = df_out[c].astype(str).replace('nan', '')

    values: List[List[Any]] = [df_out.columns.tolist()] + df_out.values.tolist()
    start_range = f"{tab_name}!A1"

    try:
        if clear_before_write:
            service.spreadsheets().values().clear(
                spreadsheetId=ssid,
                range=f"{tab_name}!A:ZZ",  # <-- FIX 1
                body={}
            ).execute()

        service.spreadsheets().values().update(
            spreadsheetId=ssid,
            range=start_range,            # <-- FIX 2
            valueInputOption=value_input_option,
            body={"values": values},
        ).execute()
        print(f"✅ Successfully wrote DataFrame to sheet: {tab_name}")
    except HttpError as e:
        print(f"An error occurred: {e}")
