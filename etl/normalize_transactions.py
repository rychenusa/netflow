"""
Normalize transaction data from various CSV formats into a canonical schema.
Maps common column names (BofA, Amex, etc.) to: date_posted, account_id,
description, merchant, category, txn_type, amount.
"""

import pandas as pd
from typing import Optional

# Canonical column names expected by the rest of the pipeline
CANONICAL_COLUMNS = [
    "date_posted",
    "account_id",
    "description",
    "merchant",
    "category",
    "txn_type",
    "amount",
]

# Common CSV column name mappings (case-insensitive match)
# debit/credit kept separate so we can combine into signed amount
COLUMN_ALIASES = {
    "date_posted": ["date", "posted date", "transaction date", "posting date", "date posted"],
    "description": ["description", "memo", "name", "transaction description", "details"],
    "amount": ["amount", "transaction amount", "total"],
    "debit": ["debit"],
    "credit": ["credit"],
    "merchant": ["merchant", "payee", "description"],
}

# Valid txn_type values
TXN_TYPES = {"purchase", "paycheck", "transfer", "refund", "fee", "other"}


def detect_columns(df: pd.DataFrame) -> dict:
    """
    Detect if CSV has required columns (date + amount or debit/credit).
    Returns dict: ok (bool), message (str), canonical_columns (list of detected canonical names).
    """
    if df is None or df.empty:
        return {"ok": False, "message": "File is empty.", "canonical_columns": []}
    normalized = _normalize_column_names(df)
    has_date = "date_posted" in normalized.columns
    has_amount = "amount" in normalized.columns
    has_debit_credit = "debit" in normalized.columns or "credit" in normalized.columns
    ok = has_date and (has_amount or has_debit_credit)
    canonical = [c for c in ["date_posted", "description", "amount", "debit", "credit", "merchant"] if c in normalized.columns]
    if ok:
        msg = f"Detected {len(df)} rows. Columns: {', '.join(canonical)}."
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

    normalized = _normalize_column_names(df)

    if "date_posted" not in normalized.columns:
        raise ValueError("Could not find a date column in the CSV.")
    has_amount = "amount" in normalized.columns
    has_debit_credit = "debit" in normalized.columns or "credit" in normalized.columns
    if not has_amount and not has_debit_credit:
        raise ValueError("Could not find amount or debit/credit columns in the CSV.")

    out = pd.DataFrame()
    out["date_posted"] = _parse_date(normalized["date_posted"])
    out["account_id"] = account_id
    out["description"] = normalized.get("description", normalized.get("merchant", "")).fillna("").astype(str)
    out["merchant"] = normalized.get("merchant", out["description"]).fillna("").astype(str)
    out["category"] = "Other"  # categorization step will overwrite
    out["txn_type"] = normalized.get("txn_type", None)

    if "debit" in normalized.columns and "credit" in normalized.columns:
        debits = _ensure_amount_decimal(normalized["debit"])
        credits = _ensure_amount_decimal(normalized["credit"])
        out["amount"] = credits - debits if amount_debit_negative else debits - credits
    elif "debit" in normalized.columns:
        out["amount"] = -_ensure_amount_decimal(normalized["debit"])
    elif "credit" in normalized.columns:
        out["amount"] = _ensure_amount_decimal(normalized["credit"])
    else:
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
