"""
Deduplication via fingerprint: hash(date_posted + account_id + description + amount).
Transactions with an existing fingerprint are skipped on insert.
"""

import hashlib
import pandas as pd
from typing import Optional


def make_fingerprint(date_posted: str, account_id: str, description: str, amount: float) -> str:
    """Generate a unique fingerprint for deduplication."""
    raw = f"{date_posted}|{account_id}|{str(description).strip()}|{amount}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def add_fingerprints(df: pd.DataFrame, account_id_col: str = "account_id") -> pd.DataFrame:
    """
    Add a 'fingerprint' column to a canonical transaction DataFrame.
    Uses date_posted, account_id, description, amount.
    """
    out = df.copy()
    if "fingerprint" in out.columns:
        return out
    out["fingerprint"] = out.apply(
        lambda row: make_fingerprint(
            str(row["date_posted"]),
            str(row.get(account_id_col, "")),
            str(row.get("description", "")),
            float(row.get("amount", 0)),
        ),
        axis=1,
    )
    return out


def filter_new_only(df: pd.DataFrame, existing_fingerprints: set) -> pd.DataFrame:
    """Return rows whose fingerprint is not in existing_fingerprints."""
    if "fingerprint" not in df.columns:
        return df
    return df[~df["fingerprint"].isin(existing_fingerprints)].copy()


def get_existing_fingerprints(conn, table: str = "transactions", user_id: Optional[int] = None) -> set:
    """Read fingerprints from transactions. If user_id is set, only that user's accounts."""
    import sqlite3
    if not isinstance(conn, sqlite3.Connection):
        raise TypeError("conn must be a sqlite3.Connection")
    if user_id is not None:
        cur = conn.execute(
            f"SELECT fingerprint FROM {table} t JOIN accounts a ON t.account_id = a.account_id AND a.user_id = ?",
            (user_id,),
        )
    else:
        cur = conn.execute(f"SELECT fingerprint FROM {table}")
    return {row[0] for row in cur.fetchall()}
