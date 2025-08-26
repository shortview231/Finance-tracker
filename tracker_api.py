# tracker_api.py
# Run:  python tracker_api.py
# Purpose: Load Ledger from Google Sheets (read-only), normalize headers,
#          and create lowercased/trimmed *_norm columns for key text fields.

import os
import sys
import pandas as pd

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# ── CONFIG ────────────────────────────────────────────────────────────────────
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]  # safe: read-only
SPREADSHEET_ID = "13tQQwyMBMI0STwFuvbif01gTSJtUCkicUcrjZBPmAkI"
RANGE_NAME = "Ledger!A:H"
TOKEN_FILE = "token.json"
CLIENT_SECRETS = "credentials.json"
# ─────────────────────────────────────────────────────────────────────────────

def get_creds() -> Credentials:
    """Authenticate with Google and return user credentials (read-only)."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CLIENT_SECRETS):
                print("❌ credentials.json not found in repo root.", file=sys.stderr)
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return creds

def fetch_ledger_dataframe(creds: Credentials) -> pd.DataFrame:
    """Fetch the Ledger range from Google Sheets and return a pandas DataFrame."""
    svc = build("sheets", "v4", credentials=creds)
    resp = svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=RANGE_NAME,
        valueRenderOption="UNFORMATTED_VALUE",   # keep numbers numeric
        dateTimeRenderOption="FORMATTED_STRING",
    ).execute()

    values = resp.get("values", [])
    if not values:
        print(f"⚠️  No data returned from range: {RANGE_NAME}")
        return pd.DataFrame()

    headers = values[0]
    rows = values[1:]
    return pd.DataFrame(rows, columns=headers)

def main():
    # Ensure stable working dir (so token/credentials save in repo root)
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # 1) Auth + load
    creds = get_creds()
    df_raw = fetch_ledger_dataframe(creds)
    if df_raw.empty:
        print("Nothing to show — your Ledger range appears empty.")
        return

    # ── import your cleaner module safely and show diagnostics ──
    import importlib
    import tracker.clean as clean
    importlib.reload(clean)  # ensure latest edits are used

    print("➡ importing tracker.clean from:", clean.__file__)
    print("➡ available names:", [n for n in dir(clean) if not n.startswith("_")])

    # pull functions off module
    normalize_columns = clean.normalize_columns
    lowercase_strings = clean.lowercase_strings

    # 2) Normalize headers (snake_case)
    df = normalize_columns(df_raw)

    # 3) Lowercase/trim key text columns -> *_norm (non-destructive)
    wanted_text_cols = ["type", "category", "payment_method", "description", "name"]
    text_cols_present = [c for c in wanted_text_cols if c in df.columns]
    df_clean = lowercase_strings(df, cols=text_cols_present, make_norm_cols=True)

    # 4) Previews
    print("\n📄 RAW PREVIEW (first 10 rows, original headers):\n")
    try:
        print(df_raw.head(10).to_string(index=False))
    except Exception:
        print(df_raw.head(10))

    print("\n✅ NORMALIZED HEADERS (snake_case):")
    print(df.columns.tolist())

    # Show original vs *_norm side-by-side for the columns we cleaned
    pairs = []
    for c in text_cols_present:
        pairs += [c, f"{c}_norm"]

    print("\n🔤 CLEANED TEXT COLUMNS (original → *_norm) — first 10 rows:\n")
    if pairs:
        try:
            print(df_clean[pairs].head(10).to_string(index=False))
        except Exception:
            print(df_clean[pairs].head(10))
    else:
        print("(No expected text columns found to clean.)")

    print(f"\nℹ️  Total data rows: {len(df)}")

if __name__ == "__main__":
    main()
