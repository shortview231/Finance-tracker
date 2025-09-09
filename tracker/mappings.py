# tracker/mappings.py

# Header aliases: messy/raw column names -> raw canonical
HEADER_ALIASES = {
    # amounts
    "amount ($)": "amount",
    "amt": "amount",
    "transaction amount": "amount",
    "amount$": "amount",
    "amount_usd": "amount",

    # dates
    "date ": "date",
    "datec": "date",                 # common typo you saw
    "transaction date": "date",
    "posted date": "date",

    # types
    "txn_type": "type",
    "transaction type": "type",

    # payment method
    "payment method": "payment_method",
    "pay_method": "payment_method",
    "method": "payment_method",
    "payment_method ": "payment_method",
    "payment-method": "payment_method",

    # posted flag
    "posted?": "posted",
    "is_posted": "posted",
    "cleared": "posted",            # many banks use "cleared" as the posted flag

    # descriptions
    "desc": "description",
    "memo": "description",
    "details": "description",

    # sources and names
    "vendor": "source",
    "merchant": "source",
    "merchant name": "source",
    "name": "name",
    "payee": "name",

    # balances
    "remaining_baalance": "remaining_balance",
    "remaining balance": "remaining_balance",
    "balance remaining": "remaining_balance",

    # add more as you discover them
}

# Normalization maps (values)
# Left side is what might appear in the sheet, right side is the canonical
TYPE_MAP = {
    # income
    "income": "income",
    "in": "income",
    "pay": "income",
    "salary": "income",
    "deposit": "income",
    "refund": "income",
    "reimbursement": "income",
    "tip": "income",
    "tips": "income",

    # expense
    "expense": "expense",
    "exp": "expense",
    "bill": "expense",
    "purchase": "expense",
    "withdrawal": "expense",
    "fee": "expense",
    "fees": "expense",

    # disability variants always treated as income
    "disability": "income",
    "ssi": "income",
    "ssdi": "income",

    # gig shorthand treated as income
    "gig": "income",
    "dd": "income",
    "doordash": "income",
}

# Common typos & canonicalization
# IMPORTANT: clean.lowercase_strings must use .replace(SPELLING_FIXES, regex=True)
SPELLING_FIXES = {
    # collapse weird repeated letters in common tokens
    r"\bdo+ordash\b": "doordash",
    r"\bgo+ogle\b": "google",
    r"\bu+ber\s*eats\b": "uber eats",
    r"\bpharm(?:a|ar)cy\b": "pharmacy",
    r"\brest(?:a)?urant\b": "restaurant",
    r"\bgro+ceries\b": "groceries",
    r"\bnetf+lix\b": "netflix",

    # space and punctuation oddities
    r"\bcash\s*app\b": "cashapp",
    r"\bapple\s*pay\b": "apple pay",
    r"\bgoogle\s*pay\b": "google pay",

    # brand and service hiccups
    r"\bdiscover\s*\b": "discover",
    r"\byou\s*tube\s*premium\b": "youtube premium",

    # your known typos
    r"\bwoek\b": "work",
    r"\bdoodash\b": "doordash",
    r"\bgrocceries\b": "groceries",

    # generic cleanups - keep conservative
    r"\s{2,}": " ",           # collapse 2+ spaces to 1
    r"^\s+|\s+$": "",         # trim ends (start or end spaces)
}

# Category normalization (raw -> stable, all lowercase)
# The right-hand side is the canonical set that clean.enforce_schema will allow.
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

    "spire": "spire",            # utilities bucket name you are using
    "utilities": "spire",

    "dining": "dining",
    "restaurant": "dining",
    "restaurants": "dining",
    "coffee": "dining",
    "fast food": "dining",
    "uber eats": "dining",
    "doordash expense": "dining",   # if any food order logged as expense

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
PAYMENT_METHOD_MAP = {
    # debit/credit
    "deb": "debit",
    "debt": "debit",
    "debit": "debit",
    "debit card": "debit",

    "credit": "credit",
    "cc": "credit",
    "visa": "credit",
    "mastercard": "credit",
    "discover": "credit",
    "amex": "credit",

    # bank and wallets
    "ach ": "ach",
    "ach": "ach",
    "zelle": "zelle",
    "paypal": "paypal",
    "apple pay": "apple_pay",
    "google pay": "google_pay",

    "cashapp": "cash_app",
    "cash app": "cash_app",
    "cash": "cash",
}

# Buckets are lowercase so they align with schema VALUE_DOMAINS
# If a category is missing here it will default in code where needed.
BUCKET_RULES = {
    # needs
    "rent": "needs",
    "groceries": "needs",
    "gas": "needs",
    "spire": "needs",
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
