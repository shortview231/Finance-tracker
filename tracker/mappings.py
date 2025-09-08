# tracker/mappings.py

# Header aliases: messy/raw column names -> raw canonical
HEADER_ALIASES = {
    "amount ($)": "amount",
    "amt": "amount",
    "transaction amount": "amount",

    "date ": "date",
    "transaction date": "date",

    "payment method": "payment_method",
    "pay_method": "payment_method",
    "method": "payment_method",

    "posted?": "posted",
    "is_posted": "posted",

    "desc": "description",
    "memo": "description",

    "vendor": "source",
    "merchant": "source",
    "name": "name",

    "remaining_baalance": "remaining_balance",  # keep your typo alias
    # add more as you discover them
}

# Normalization maps (values)
# Left side is what might appear in the sheet, right side is the canonical
TYPE_MAP = {
    # core
    "income": "income",
    "in": "income",
    "pay": "income",
    "salary": "income",
    "deposit": "income",
    "refund": "income",

    "expense": "expense",
    "exp": "expense",
    "bill": "expense",
    "purchase": "expense",
    "withdrawal": "expense",

    # disability variants always treated as income
    "disability": "income",
    "ssi": "income",
    "ssdi": "income",

    # gig shorthand treated as income
    "gig": "income",
    "dd": "income",
    "doordash": "income",
}

# Common typos & canonicalization (low-stakes spelling)
SPELLING_FIXES = {
    "woek": "work",
    "doodash": "doordash",
    "grocceries": "groceries",
    "discover ": "discover",
    "goggle": "google",
    "cash app": "cashapp",
    "uber  eats": "uber eats",
    "pharamcy": "pharmacy",
    "restuarant": "restaurant",
    # quiet demo sources if desired
    "demo": "demo",
}

# Category normalization (raw -> stable, all lowercase)
# IMPORTANT: Values here are the canonical set that clean.enforce_schema will allow.
CATEGORY_MAP = {
    # income-like
    "dd": "doordash",
    "doordash": "doordash",
    "gig": "doordash",
    "disability": "disability",
    "ssi": "disability",
    "ssdi": "disability",

    # common expenses
    "groceries": "groceries",
    "grocery": "groceries",
    "grocs": "groceries",

    "gas": "gas",
    "fuel": "gas",

    "rent": "rent",

    "phone": "phone",
    "cell": "phone",
    "cell phone": "phone",

    "spire": "spire",           # utilities
    "utilities": "spire",

    "dining": "dining",
    "restaurant": "dining",
    "restaurants": "dining",
    "coffee": "dining",
    "fast food": "dining",
    "uber eats": "dining",
    "doordash expense": "dining",  # if any food order categorized as expense

    "entertainment": "entertainment",
    "streaming": "entertainment",
    "netflix": "entertainment",
    "hulu": "entertainment",
    "spotify": "entertainment",
    "youtube premium": "entertainment",

    "medicine": "medicine",
    "pharmacy": "medicine",

    "weed": "weed",

    "misc": "misc",
    "other": "misc",
    "unknown": "misc",
}

# Payment method normalization (raw -> stable)
# Keep it simple. You can expand as you see these in the wild.
PAYMENT_METHOD_MAP = {
    "deb": "debit",
    "debt": "debit",
    "debit card": "debit",

    "credit": "credit",
    "cc": "credit",
    "visa": "credit",
    "mastercard": "credit",
    "discover": "credit",
    "amex": "credit",

    "ach ": "ach",
    "ach": "ach",
    "zelle": "zelle",
    "paypal": "paypal",
    "apple pay": "apple_pay",
    "google pay": "google_pay",

    "cashapp": "cash_app",
    "cash": "cash",
}

# Buckets are lowercase so they align with schema VALUE_DOMAINS
# If a category is missing here it will default in code where needed.
BUCKET_RULES = {
    # needs
    "rent": "needs",
    "groceries": "needs",
    "gas": "needs",
    "spire": "needs",          # utilities
    "phone": "needs",
    "medicine": "needs",

    # wants
    "entertainment": "wants",
    "dining": "wants",
    "weed": "wants",
    "misc": "wants",

    # income
    "doordash": "income",
    "disability": "income",
}
