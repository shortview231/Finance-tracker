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
    Load config.toml. Expected keys:

    [google]
    spreadsheet_id = "..."
    calendar_id = "primary"
    timezone = "America/Chicago"
    token_path = "token.json"        # optional; default 'token.json'

    [ranges]
    ledger = "Ledger!A:Z"            # preferred; overrides tab_name/col_range

    # Legacy:
    [sheets]
    spreadsheet_id = "..."
    ledger_tab = "Ledger"
    """
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
            "ledger = \"Ledger!A:Z\"\n"
        )
    with cfg_path.open("rb") as f:
        return tomllib.load(f)


def _get_google_sheet_id(cfg: Dict[str, Any]) -> str:
    ssid = (
        cfg.get("google", {}).get("spreadsheet_id")
        or cfg.get("sheets", {}).get("spreadsheet_id")
    )
    if not ssid:
        raise ValueError("Missing spreadsheet_id (expected under [google] or [sheets]).")
    return ssid


def _get_token_path(cfg: Dict[str, Any]) -> Path:
    return Path(cfg.get("google", {}).get("token_path", "token.json"))


def _get_ledger_range(cfg: Dict[str, Any], tab_name: Optional[str], col_range: Optional[str]) -> str:
    """
    If [ranges].ledger is present, use it; else compose from tab_name/legacy config + col_range.
    """
    if cfg.get("ranges", {}).get("ledger"):
        return cfg["ranges"]["ledger"]
    tab = tab_name or cfg.get("sheets", {}).get("ledger_tab", "Ledger")
    cr = col_range or "A:Z"
    return f"{tab}!{cr}"


# =========================
# Google Sheets: auth / service
# =========================
# Always request full spreadsheets scope (includes read + write)
READONLY_SCOPE = ["https://www.googleapis.com/auth/spreadsheets"]
WRITE_SCOPE    = ["https://www.googleapis.com/auth/spreadsheets"]
                                                                                                                                                                                                                                                         
def _get_credentials(scopes: List[str]) -> Credentials:
    """
    Retrieve credentials for the given scopes. If an existing token lacks
    the required scopes, automatically delete it and re-run OAuth to upgrade.
    """
    cfg = _load_config()
    token_path = _get_token_path(cfg)

    creds: Optional[Credentials] = None
    if token_path.exists():
        # Load token with requested scopes; if insufficient, nuke and re-consent
        tmp = Credentials.from_authorized_user_file(str(token_path), scopes)
        token_scopes = set(tmp.scopes or [])
        required_scopes = set(scopes)
        if required_scopes.issubset(token_scopes):
            creds = tmp
        else:
            # 🔥 Remove stale token so we don't reuse a read-only token for writes
            try:
                token_path.unlink()
                print(f"ℹ️ Removed stale token with insufficient scopes: {token_path}")
            except Exception:
                pass
            creds = None  # force OAuth below

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not Path("credentials.json").exists():
                raise FileNotFoundError(
                    "credentials.json not found in repo root. "
                    "Download OAuth client credentials from Google Cloud Console and place it here."
                )
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", scopes)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())

    return creds


def _get_sheets_service(scopes: Optional[List[str]] = None):
    """
    Build the Sheets API service with the given scopes.
    - Read-only:  READONLY_SCOPE
    - Read/Write: WRITE_SCOPE
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
def read_ledger_from_sheets(
    spreadsheet_id: Optional[str] = None,
    tab_name: Optional[str] = None,   # ignored if [ranges].ledger is set
    col_range: Optional[str] = None,  # ignored if [ranges].ledger is set
) -> pd.DataFrame:
    """
    Read the Ledger into a DataFrame.
    Supports both new ([google]/[ranges]) and legacy ([sheets]) config styles.
    """
    cfg = _load_config()
    ssid = spreadsheet_id or _get_google_sheet_id(cfg)
    range_str = _get_ledger_range(cfg, tab_name, col_range)

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
    # If rows length varies, pad to header len to avoid jagged frames
    fixed_rows: List[List[str]] = [r + [""] * (len(header) - len(r)) for r in rows]
    return pd.DataFrame(fixed_rows, columns=header)


def write_df_to_sheet(
    df: pd.DataFrame,
    spreadsheet_id: Optional[str] = None,
    tab_name: str = "Ledger_CLEAN",
    clear_before_write: bool = True,
    value_input_option: str = "RAW",  # or "USER_ENTERED"
) -> None:
    """
    Write a DataFrame to a Sheet tab (overwrites by default).
    - Ensures write scope (auto re-consent if token lacks it).
    - Auto-creates tab if missing.
    - Clears tab (A:ZZ) if requested, then writes starting at A1 with header.
    """
    cfg = _load_config()
    ssid = spreadsheet_id or _get_google_sheet_id(cfg)

    # Build service with WRITE scope (will re-prompt if your token was read-only)
    service = _get_sheets_service(scopes=WRITE_SCOPE)

    # Ensure the destination tab exists
    _ensure_sheet_tab(service, ssid, tab_name)

    # Convert DataFrame to values (strings are safest across typed columns)
    df_out = df.copy()
    # Format datetime-like columns as YYYY-MM-DD for Sheets
    for c in df_out.columns:
        if pd.api.types.is_datetime64_any_dtype(df_out[c]):
            df_out[c] = pd.to_datetime(df_out[c], errors="coerce").dt.strftime("%Y-%m-%d")
        else:
            df_out[c] = df_out[c].astype(str)

    values: List[List[str]] = [df_out.columns.tolist()] + df_out.values.tolist()
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
    except HttpError as e:
        if e.resp.status == 403:
            raise PermissionError(
                "Google Sheets API returned 403 (forbidden). "
                "Your token likely lacks the 'spreadsheets' write scope or your account lacks Editor permission. "
                "Fix: ensure the Sheet grants Editor access to this account."
            ) from e
        raise
