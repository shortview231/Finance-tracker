# tracker/schema.py
from typing import Mapping, Iterable, List, Dict, Any
# This file is a central repository for the schema and mappings
# It should be imported by other modules to ensure consistency.

# Raw columns required in the input data
RAW_REQUIRED: List[str] = ["date", "type", "amount"]

# Raw optional columns and their default values
RAW_OPTIONAL_DEFAULTS: Dict[str, Any] = {
    "category": "misc",
    "description": "",
    "source": "",
    "posted": "true",
    "name": ""
}

# Final canonical headers for the cleaned output dataframe
CLEAN_HEADERS: List[str] = [
    "date_dt", "amount_signed", "amount_num", "type_norm", "category_norm",
    "description_norm", "source_norm", "payment_method_norm", "bucket", "posted",
]

# A canonical mapping of text values to their normalized forms
VALUE_DOMAINS: Dict[str, List[str]] = {
    "type": ["income", "expense", "transfer"],
    "bucket": ["income", "needs", "wants", "savings", "taxes"],
    # Add more domains for validation as needed
}