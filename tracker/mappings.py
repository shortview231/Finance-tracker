# tracker/mappings.py

# Header aliases: messy/raw column names -> raw canonical
HEADER_ALIASES = {
    "amount ($)": "amount",
    "payment method": "payment_method",
    "pay_method": "payment_method",
    "posted?": "posted",
    "desc": "description",
    "remaining_baalance": "remaining_balance",
    # add as you find more
}

# Normalization maps (values)
TYPE_MAP = {
    "income": "income", "in": "income", "pay": "income", "salary": "income",
    "expense": "expense", "exp": "expense", "bill": "expense",
}

# Common typos & canonicalization (low-stakes spelling)
SPELLING_FIXES = {
    "woek": "work",
    "doodash": "doordash",
    "grocceries": "groceries",
    "discover ": "discover",
}

# Category normalization (raw -> stable)
CATEGORY_MAP = {
    "doodash": "doordash",
    "dd": "doordash",
    "grocceries": "groceries",
    "rent ": "rent",
    "gasoline": "gas",
    # extend as you see real data
}

# Payment method normalization
PAYMENT_METHOD_MAP = {
    "deb": "debit",
    "debt": "debit",
    "ach ": "ach",
    "cashapp": "cash_app",
    "cash app": "cash_app",
}

# Simple bucket rules (can move to regex later)
BUCKET_RULES = {
    "rent": "Needs",
    "groceries": "Needs",
    "gas": "Needs",
    "spire": "Needs",
    "phone": "Needs",
    "weed": "Wants",
    "doordash": "Income",
}
