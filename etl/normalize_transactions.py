"""
Normalize transaction data from various CSV formats into a canonical schema.
Maps common column names (BofA, Amex, etc.) to: date_posted, account_id,
description, merchant, category, txn_type, amount.

Includes normalize_columns() to handle messy bank exports (e.g. "Summary Amt.",
"Posted Date", "Unnamed: 1") before the rest of the ETL runs.
"""

import re
import pandas as pd
from typing import Optional, Union, BinaryIO, TextIO

# Canonical column names expected by the rest of the pipeline (date_posted used internally)
CANONICAL_COLUMNS = [
    "date_posted",
    "account_id",
    "description",
    "merchant",
    "category",
    "txn_type",
    "amount",
]

# ---------------------------------------------------------------------------
# normalize_columns() canonical output: date, description, amount
# (Pipeline then uses date_posted = date, etc.)
# ---------------------------------------------------------------------------
# Aliases for the initial column normalization step (messy bank exports).
# Order matters: first match wins when multiple columns could match.
NORMALIZE_DATE_ALIASES = [
    "posted date",
    "transaction date",
    "date",
    "posting date",
    "date posted",
    "unnamed: 1",  # Pandas often names a second date column "Unnamed: 1"
]
NORMALIZE_DESCRIPTION_ALIASES = [
    "description",
    "payee",
    "merchant",
    "details",
    "memo",
    "name",
    "transaction description",
]
NORMALIZE_AMOUNT_ALIASES = [
    "amount",
    "summary amt.",
    "summary amt",
    "amt",
    "transaction amount",
    "total",
]
# Debit/credit column names (for amount = credit - debit)
NORMALIZE_DEBIT_ALIASES = ["debit", "debits"]
NORMALIZE_CREDIT_ALIASES = ["credit", "credits"]

# Common CSV column name mappings (case-insensitive) for _normalize_column_names
# debit/credit kept separate so we can combine into signed amount
COLUMN_ALIASES = {
    "date_posted": ["date", "posted date", "transaction date", "posting date", "date posted", "unnamed: 1"],
    "description": ["description", "memo", "name", "transaction description", "details", "payee", "merchant"],
    "amount": ["amount", "transaction amount", "total", "summary amt.", "summary amt", "amt"],
    "debit": ["debit", "debits"],
    "credit": ["credit", "credits"],
    "merchant": ["merchant", "payee", "description"],
}

# Valid txn_type values
TXN_TYPES = {"purchase", "paycheck", "transfer", "refund", "fee", "other"}

# Summary row markers to drop when extracting transaction section (multi-section bank CSVs)
SUMMARY_ROW_MARKERS = (
    "beginning balance",
    "total credits",
    "total debits",
    "ending balance",
)


def extract_transaction_section(
    file_or_path: Union[str, BinaryIO, TextIO],
    encoding: str = "utf-8",
) -> pd.DataFrame:
    """
    Extract the transaction table from a bank CSV that has a summary block at the top.

    Some exports (e.g. BofA) have:
    - Lines 1–5: Summary (Description, Summary Amt. / Beginning balance, Total credits, ...)
    - Blank line
    - Then: Date, Description, Amount, Running Bal.
    - Then: transaction rows

    This function reads the file with no header, finds the row where the first column
    is "Date" (or similar), uses that row as the header, and returns the transaction
    DataFrame. Drops summary rows and empty rows.
    """
    try:
        df_raw = pd.read_csv(file_or_path, header=None, encoding=encoding, on_bad_lines="skip")
    except Exception:
        df_raw = pd.read_csv(file_or_path, header=None, encoding="latin-1", on_bad_lines="skip")
    if df_raw.empty or len(df_raw) < 2:
        return pd.DataFrame()

    # Find the row that looks like the transaction table header (first cell = "date", etc.)
    header_row_idx = None
    for i in range(min(len(df_raw), 20)):  # check first 20 rows
        row = df_raw.iloc[i]
        first = str(row.iloc[0]).strip().lower() if len(row) > 0 else ""
        if first == "date" or (first.startswith("date") and "description" in " ".join(str(x).lower() for x in row)):
            header_row_idx = i
            break
    if header_row_idx is None:
        return pd.DataFrame()

    # Use that row as column names, rest as data
    df = df_raw.iloc[header_row_idx + 1 :].copy()
    df.columns = [str(x).strip() for x in df_raw.iloc[header_row_idx]]
    df.reset_index(drop=True, inplace=True)

    # Drop rows that are summary or empty
    def is_summary_or_empty(row) -> bool:
        # Empty row: first column (date) empty
        first = str(row.iloc[0]).strip().lower() if len(row) > 0 else ""
        if not first or first in ("nan", "nat"):
            return True
        # Summary row: in transaction block, description (2nd col) may be "Beginning balance...", "Total credits", etc.
        desc = str(row.iloc[1]).strip().lower() if len(row) > 1 else ""
        return any(m in desc for m in SUMMARY_ROW_MARKERS)

    mask = ~df.apply(is_summary_or_empty, axis=1)
    df = df.loc[mask].copy()

    # Strip quotes from amount-like columns (e.g. "4,000.00" -> 4000.00 handled later)
    for c in df.columns:
        if "amount" in str(c).lower() or "amt" in str(c).lower():
            df[c] = df[c].astype(str).str.replace(r'^["\']|["\']$', "", regex=True)
    return df


def _series_to_amount(series: pd.Series) -> pd.Series:
    """Convert a series to numeric amount (strip $ and commas)."""
    s = pd.to_numeric(series.astype(str).str.replace(r"[\$,]", "", regex=True), errors="coerce")
    return s.fillna(0).astype(float)


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize messy bank export columns to canonical schema: date, description, amount.

    Run this before the rest of the ETL pipeline so that:
    - Column names are lowercase and stripped of whitespace
    - Common bank column names are mapped to date, description, amount
    - Debit/credit columns are combined into a single amount (credit - debit;
      spending/outflows are negative)

    Canonical output columns: date, description, amount.
    The rest of the system uses date_posted (same as date), description, amount.
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=["date", "description", "amount"])

    # 1. Normalize column names: lowercase, strip, collapse multiple spaces
    def norm_col(name: str) -> str:
        s = str(name).strip().lower()
        s = re.sub(r"\s+", " ", s)
        return s

    result = df.copy()
    result.columns = [norm_col(c) for c in result.columns]
    col_list = list(result.columns)

    def first_match(aliases: list) -> Optional[str]:
        """Return first column name that matches any alias (exact or alias in col name)."""
        for alias in aliases:
            alias_lower = alias.lower().strip()
            for col in col_list:
                if col == alias_lower or alias_lower in col:
                    return col
        return None

    def col_contains(*parts: str) -> Optional[str]:
        """Return first column that contains all of the given substrings (for flexible matching)."""
        for col in col_list:
            col_lower = col.lower()
            if all(p.lower() in col_lower for p in parts):
                return col
        return None

    # 2. Map to canonical: date, description, amount (or debit/credit)
    date_col = first_match(NORMALIZE_DATE_ALIASES)
    desc_col = first_match(NORMALIZE_DESCRIPTION_ALIASES)
    amount_col = first_match(NORMALIZE_AMOUNT_ALIASES)
    debit_col = first_match(NORMALIZE_DEBIT_ALIASES)
    credit_col = first_match(NORMALIZE_CREDIT_ALIASES)

    # 2b. Fallbacks for common bank layouts: "Description", "Unnamed: 1", "Summary Amt."
    if date_col is None and col_contains("unnamed"):
        date_col = col_contains("unnamed")
    if amount_col is None and col_contains("summary", "amt"):
        amount_col = col_contains("summary", "amt")
    if amount_col is None and col_contains("amt"):
        amount_col = col_contains("amt")

    # 3. Build output with only date, description, amount
    out = pd.DataFrame(index=result.index)

    if date_col is not None:
        out["date"] = result[date_col]
    else:
        out["date"] = pd.NA

    if desc_col is not None:
        out["description"] = result[desc_col].fillna("").astype(str)
    else:
        out["description"] = ""

    # 4. Amount: prefer single amount column; else combine debit/credit (amount = credit - debit)
    if debit_col is not None and credit_col is not None:
        # Both columns present: amount = credit - debit (outflows negative)
        out["amount"] = _series_to_amount(result[credit_col]) - _series_to_amount(result[debit_col])
    elif debit_col is not None:
        # Only debit: amount = -debit
        out["amount"] = -_series_to_amount(result[debit_col])
    elif credit_col is not None:
        # Only credit: amount = credit
        out["amount"] = _series_to_amount(result[credit_col])
    elif amount_col is not None:
        out["amount"] = _series_to_amount(result[amount_col])
    else:
        out["amount"] = 0.0

    return out


def detect_columns(df: pd.DataFrame) -> dict:
    """
    Detect if CSV has required columns (date + amount or debit/credit).
    Uses normalize_columns so messy bank exports (e.g. Description, Unnamed: 1, Summary Amt.)
    are recognized.
    Returns dict: ok (bool), message (str), canonical_columns (list of detected canonical names).
    """
    if df is None or df.empty:
        return {"ok": False, "message": "File is empty.", "canonical_columns": []}
    # Run column normalization so we detect based on canonical date, description, amount
    normalized = normalize_columns(df)
    # Require date and amount columns to exist (date may have NaNs in some rows)
    has_date = "date" in normalized.columns
    has_amount = "amount" in normalized.columns
    ok = has_date and has_amount
    canonical = ["date", "description", "amount"]
    if ok:
        msg = f"Detected {len(normalized)} rows. Columns: {', '.join(canonical)}."
    else:
        need = "date and amount (or debit/credit)"
        msg = f"Missing required columns ({need}). Your file has: {list(df.columns)}."
    return {"ok": ok, "message": msg, "canonical_columns": canonical}


def _normalize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Map source columns to canonical names using alias table."""
    result = df.copy()
    result.columns = [str(c).strip() for c in result.columns]
    col_lower = {c: c.lower() for c in result.columns}

    # For each canonical name, find first matching source column
    rename_map = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in [canonical] + aliases:
            alias_lower = alias.lower()
            for src_col in result.columns:
                if col_lower[src_col] == alias_lower or alias_lower in col_lower[src_col]:
                    rename_map[src_col] = canonical
                    break
            if canonical in rename_map.values():
                break

    # rename_map is src_col -> canonical; invert so we have one canonical per source
    inv = {}
    for src, can in rename_map.items():
        if can not in inv:
            inv[can] = src
    result = result.rename(columns={v: k for k, v in inv.items()})
    return result


def _parse_date(series: pd.Series) -> pd.Series:
    """Parse date column to YYYY-MM-DD string."""
    out = pd.to_datetime(series, errors="coerce")
    return out.dt.strftime("%Y-%m-%d")


def _ensure_amount_decimal(series: pd.Series, spending_negative: bool = True) -> pd.Series:
    """Convert amount to float. Optionally treat debits as negative."""
    s = pd.to_numeric(series.replace(r"[\$,]", "", regex=True), errors="coerce")
    return s.fillna(0).astype(float)


def _infer_txn_type(row: pd.Series) -> str:
    """Infer txn_type from description/amount if not provided."""
    desc = str(row.get("description", "")).upper()
    amount = row.get("amount", 0)
    if "PAYCHECK" in desc or "SALARY" in desc or "DIRECT DEP" in desc:
        return "paycheck"
    if "TRANSFER" in desc or "XFER" in desc:
        return "transfer"
    if "REFUND" in desc:
        return "refund"
    if "FEE" in desc or "FEE " in desc:
        return "fee"
    if amount and float(amount) > 0:
        return "paycheck"  # default positive to paycheck if not transfer/refund
    return "purchase"


def normalize_to_canonical(
    df: pd.DataFrame,
    account_id: str,
    date_format: Optional[str] = None,
    amount_debit_negative: bool = True,
) -> pd.DataFrame:
    """
    Convert a raw transaction DataFrame to canonical schema.

    Parameters
    ----------
    df : pd.DataFrame
        Raw transaction data (any column names).
    account_id : str
        Account identifier (e.g. bofa_checking, amex_gold).
    date_format : str, optional
        strftime format for date column (e.g. '%m/%d/%Y'). If None, pandas infers.
    amount_debit_negative : bool
        If True, treat debit/outflow as negative. Default True.

    Returns
    -------
    pd.DataFrame with columns: date_posted, account_id, description, merchant,
    category, txn_type, amount.
    """
    if df.empty:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)

    # Column normalization step: messy bank exports -> canonical date, description, amount
    df = normalize_columns(df)
    # Map canonical "date" to internal "date_posted" and ensure we have required columns
    normalized = _normalize_column_names(df)

    if "date_posted" not in normalized.columns:
        raise ValueError("Could not find a date column in the CSV.")
    if "amount" not in normalized.columns:
        raise ValueError("Could not find an amount column in the CSV.")

    out = pd.DataFrame()
    out["date_posted"] = _parse_date(normalized["date_posted"])
    out["account_id"] = account_id
    out["description"] = normalized.get("description", normalized.get("merchant", "")).fillna("").astype(str)
    out["merchant"] = normalized.get("merchant", out["description"]).fillna("").astype(str)
    out["category"] = "Other"  # categorization step will overwrite
    out["txn_type"] = normalized.get("txn_type", None)

    # Amount: normalize_columns already produced a single "amount" column (credit - debit when applicable)
    out["amount"] = _ensure_amount_decimal(normalized["amount"], spending_negative=amount_debit_negative)

    # Infer txn_type where missing
    mask = out["txn_type"].isna() | (out["txn_type"].astype(str).str.strip() == "")
    for i in out.index[mask]:
        out.loc[i, "txn_type"] = _infer_txn_type(out.loc[i])

    out["txn_type"] = out["txn_type"].replace("", "other").fillna("other")
    out["txn_type"] = out["txn_type"].apply(
        lambda x: x if x in TXN_TYPES else "other"
    )

    return out[CANONICAL_COLUMNS]
