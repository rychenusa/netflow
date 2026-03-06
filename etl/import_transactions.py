"""
Transaction import pipeline: read CSV -> normalize -> categorize -> dedupe -> insert.
Upserts account if missing. Uses fingerprint to skip duplicate transactions.
Uses file_hash in imports table to skip duplicate file uploads.
"""

import hashlib
import os
import sqlite3
from datetime import datetime
from typing import Optional

import pandas as pd

from .normalize_transactions import normalize_to_canonical, CANONICAL_COLUMNS
from .categorize import categorize_transactions
from .dedupe import add_fingerprints, filter_new_only, get_existing_fingerprints

# Project root (parent of etl/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB_PATH = os.path.join(PROJECT_ROOT, "db", "finance.db")

INSERT_COLUMNS = CANONICAL_COLUMNS + ["fingerprint"]


def compute_file_hash_from_bytes(content: bytes) -> str:
    """Compute SHA-256 hash of file content for duplicate detection."""
    return hashlib.sha256(content).hexdigest()


def compute_file_hash_from_dataframe(df: pd.DataFrame) -> str:
    """Compute hash of DataFrame as CSV bytes so same data => same hash."""
    content = df.to_csv(index=False).encode("utf-8")
    return compute_file_hash_from_bytes(content)


def compute_file_hash_from_path(csv_path: str, encoding: str = "utf-8") -> str:
    """Compute hash of a CSV file on disk."""
    with open(csv_path, "rb") as f:
        return compute_file_hash_from_bytes(f.read())


def ensure_schema(conn: sqlite3.Connection, schema_path: Optional[str] = None) -> None:
    """Create tables if they do not exist. Run migrations for import_id and user_id."""
    path = schema_path or os.path.join(PROJECT_ROOT, "models", "schema.sql")
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()
    # Migration: add import_id to transactions if missing
    cur = conn.execute("PRAGMA table_info(transactions)")
    columns = [row[1] for row in cur.fetchall()]
    if "import_id" not in columns:
        conn.execute("ALTER TABLE transactions ADD COLUMN import_id INTEGER")
        conn.commit()
    # Migration: add user_id to accounts for per-user privacy
    cur = conn.execute("PRAGMA table_info(accounts)")
    acct_columns = [row[1] for row in cur.fetchall()]
    if "user_id" not in acct_columns:
        conn.execute("ALTER TABLE accounts ADD COLUMN user_id INTEGER")
        conn.commit()
        # Assign existing accounts to a default user so existing DBs keep working
        try:
            import bcrypt
            default_hash = bcrypt.hashpw(b"default", bcrypt.gensalt()).decode()
        except Exception:
            default_hash = ""  # fallback; app will require sign-up
        cur = conn.execute("SELECT 1 FROM users WHERE user_id = 1")
        if cur.fetchone() is None:
            conn.execute(
                "INSERT INTO users (user_id, username, password_hash, created_at) VALUES (1, 'default', ?, datetime('now'))",
                (default_hash or "x",),
            )
        conn.execute("UPDATE accounts SET user_id = 1 WHERE user_id IS NULL")
        conn.commit()


def ensure_account(
    conn: sqlite3.Connection,
    account_id: str,
    user_id: int,
    account_name: Optional[str] = None,
    account_type: str = "cash",
    institution: Optional[str] = None,
) -> None:
    """Insert account if not present. user_id required for per-user data."""
    cur = conn.execute(
        "SELECT 1 FROM accounts WHERE account_id = ? AND user_id = ?", (account_id, user_id)
    )
    if cur.fetchone():
        return
    conn.execute(
        "INSERT INTO accounts (account_id, user_id, account_name, account_type, institution) VALUES (?, ?, ?, ?, ?)",
        (account_id or account_id, user_id, account_name or account_id, account_type, institution or ""),
    )
    conn.commit()


def _import_hash_exists(conn: sqlite3.Connection, file_hash: str, user_id: int) -> bool:
    """Return True if this file_hash was already imported for this user (skip duplicate uploads)."""
    cur = conn.execute(
        "SELECT 1 FROM imports i JOIN accounts a ON i.account_id = a.account_id AND a.user_id = ? WHERE i.file_hash = ?",
        (user_id, file_hash),
    )
    return cur.fetchone() is not None


def _next_import_id(conn: sqlite3.Connection) -> int:
    """Return the smallest import_id >= 1 that is not in use (reuse IDs after deletes)."""
    cur = conn.execute("SELECT import_id FROM imports ORDER BY import_id")
    used = {row[0] for row in cur.fetchall()}
    k = 1
    while k in used:
        k += 1
    return k


def _create_import_record(
    conn: sqlite3.Connection,
    file_name: Optional[str],
    account_id: str,
    row_count: int,
    file_hash: str,
) -> int:
    """Insert into imports table and return import_id. Reuses lowest available ID after deletes."""
    import_date = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    import_id = _next_import_id(conn)
    conn.execute(
        """INSERT INTO imports (import_id, file_name, account_id, import_date, row_count, file_hash)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (import_id, file_name or "", account_id, import_date, row_count, file_hash),
    )
    conn.commit()
    return import_id


def import_from_dataframe(
    df: pd.DataFrame,
    account_id: str,
    conn: sqlite3.Connection,
    user_id: int,
    account_name: Optional[str] = None,
    account_type: str = "cash",
    institution: Optional[str] = None,
    rules_path: Optional[str] = None,
    file_name: Optional[str] = None,
) -> int:
    """
    Normalize, categorize, dedupe, and insert transactions. Creates account if needed.
    user_id scopes data to that user. Skips if file_hash already imported for this user.
    Returns number of rows inserted.
    """
    if df.empty:
        return 0

    file_hash = compute_file_hash_from_dataframe(df)
    if _import_hash_exists(conn, file_hash, user_id):
        return 0  # Duplicate file upload for this user; skip

    ensure_account(conn, account_id, user_id, account_name, account_type, institution)

    normalized = normalize_to_canonical(df, account_id=account_id)
    categorized = categorize_transactions(normalized, rules_path=rules_path)
    with_fp = add_fingerprints(categorized)
    existing = get_existing_fingerprints(conn, user_id=user_id)
    new_df = filter_new_only(with_fp, existing)

    row_count = len(new_df)
    import_id = _create_import_record(
        conn, file_name, account_id, row_count, file_hash
    )

    for _, row in new_df[INSERT_COLUMNS].iterrows():
        conn.execute(
            """INSERT INTO transactions
               (date_posted, account_id, description, merchant, category, txn_type, amount, fingerprint, import_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(row["date_posted"]),
                str(row["account_id"]),
                str(row["description"]),
                str(row["merchant"]),
                str(row["category"]),
                str(row["txn_type"]),
                float(row["amount"]),
                str(row["fingerprint"]),
                import_id,
            ),
        )
    conn.commit()
    return row_count


def import_from_csv(
    csv_path: str,
    account_id: str,
    db_path: str = None,
    user_id: int = 1,
    account_name: Optional[str] = None,
    account_type: str = "cash",
    institution: Optional[str] = None,
    rules_path: Optional[str] = None,
    encoding: str = "utf-8",
) -> int:
    """
    Read CSV from path, run full pipeline, insert into SQLite.
    user_id defaults to 1 for CLI use. Returns number of new transactions inserted.
    """
    db_path = db_path or DEFAULT_DB_PATH
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    df = pd.read_csv(csv_path, encoding=encoding, on_bad_lines="skip")
    file_name = os.path.basename(csv_path)
    conn = sqlite3.connect(db_path)
    try:
        ensure_schema(conn)
        return import_from_dataframe(
            df, account_id, conn, user_id,
            account_name=account_name,
            account_type=account_type,
            institution=institution,
            rules_path=rules_path,
            file_name=file_name,
        )
    finally:
        conn.close()


def import_from_raw_dataframe(
    df: pd.DataFrame,
    account_id: str,
    db_path: str = None,
    user_id: int = None,
    account_name: Optional[str] = None,
    account_type: str = "cash",
    institution: Optional[str] = None,
    rules_path: Optional[str] = None,
    file_name: Optional[str] = None,
) -> int:
    """
    Run full pipeline on an in-memory DataFrame (e.g. from paste or CSV upload).
    user_id required for per-user data. Pass file_name when uploading a file.
    """
    if user_id is None:
        raise ValueError("user_id is required for import_from_raw_dataframe")
    db_path = db_path or DEFAULT_DB_PATH
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        ensure_schema(conn)
        return import_from_dataframe(
            df, account_id, conn, user_id,
            account_name=account_name,
            account_type=account_type,
            institution=institution,
            rules_path=rules_path,
            file_name=file_name,
        )
    finally:
        conn.close()
