# tracker_api.py
# When you run: python tracker_api.py
# It will show you the first 10 rows from your Google Sheet (Ledger!A:H).

import os, sys
import pandas as pd
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# 👇 your sheet ID from the URL
SPREADSHEET_ID = "13tQQwyMBMI0STwFuvbif01gTSJtUCkicUcrjZBPmAkI"
RANGE_NAME = "Ledger!A:H"   # adjust if tab/range is different

def get_creds():
    token_file = "token.json"
    creds = None
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists("credentials.json"):
                print("❌ credentials.json not found", file=sys.stderr)
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, "w") as f:
            f.write(creds.to_json())
    return creds

def main():
    creds = get_creds()
    service = build("sheets", "v4", credentials=creds)
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME
    ).execute()
    values = result.get("values", [])

    if not values:
        print("(No data found in sheet)")
        return

    # Assume first row is headers
    df = pd.DataFrame(values[1:], columns=values[0])
    print("\n📄 Preview of your sheet:\n")
    print(df.head(10).to_string(index=False))
    print(f"\nTotal rows (including header): {len(values)}")

if __name__ == "__main__":
    main()
