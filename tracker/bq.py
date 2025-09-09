# tracker/bq.py
# Handles BigQuery uploads for Finance-tracker

import pandas_gbq
import toml
from google.oauth2 import service_account

# Load config
config = toml.load("config.toml")
bq_conf = config["bigquery"]

def upload_to_bigquery(df):
    """
    Uploads a pandas DataFrame to BigQuery using config.toml settings.
    """
    project_id = bq_conf["project_id"]
    dataset = bq_conf["dataset"]
    table = bq_conf["table"]
    credentials_path = bq_conf["credentials_json"]

    # Build credentials object from service account JSON
    creds = service_account.Credentials.from_service_account_file(credentials_path)

    # Full table name: dataset.table
    table_id = f"{dataset}.{table}"

    print(f"⏫ Uploading DataFrame to BigQuery → {project_id}:{table_id}")

    pandas_gbq.to_gbq(
        df,
        table_id,
        project_id=project_id,
        if_exists="replace",   # or "append"
        progress_bar=True,
        credentials=creds
    )

    print(f"✅ Upload complete: {project_id}.{table_id}")
