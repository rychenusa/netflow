-- Netflow - SQLite Schema
-- Run this to initialize finance.db

-- ---------------------------------------------------------------------------
-- ACCOUNTS
-- account_type: cash | credit | investment | alternative | loan
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS accounts (
    account_id TEXT PRIMARY KEY,
    account_name TEXT,
    account_type TEXT NOT NULL,
    institution TEXT
);

-- ---------------------------------------------------------------------------
-- IMPORTS
-- Tracks each CSV/file import to prevent duplicate uploads (by file_hash)
-- and to associate transactions with their source import (import_id).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS imports (
    import_id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT,
    account_id TEXT,
    import_date TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    file_hash TEXT NOT NULL,
    FOREIGN KEY (account_id) REFERENCES accounts(account_id),
    UNIQUE(file_hash)
);

CREATE INDEX IF NOT EXISTS idx_imports_file_hash ON imports(file_hash);
CREATE INDEX IF NOT EXISTS idx_imports_account ON imports(account_id);

-- ---------------------------------------------------------------------------
-- TRANSACTIONS
-- amount: spending = negative, income = positive
-- txn_type: purchase | paycheck | transfer | refund | fee | other
-- fingerprint: for deduplication (date_posted + account_id + description + amount)
-- import_id: links to imports table so we know which file each row came from
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS transactions (
    txn_id INTEGER PRIMARY KEY AUTOINCREMENT,
    date_posted TEXT NOT NULL,
    account_id TEXT NOT NULL,
    description TEXT,
    merchant TEXT,
    category TEXT,
    txn_type TEXT NOT NULL,
    amount REAL NOT NULL,
    fingerprint TEXT UNIQUE NOT NULL,
    import_id INTEGER,
    FOREIGN KEY (account_id) REFERENCES accounts(account_id),
    FOREIGN KEY (import_id) REFERENCES imports(import_id)
);

CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date_posted);
CREATE INDEX IF NOT EXISTS idx_transactions_account ON transactions(account_id);
CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions(category);
CREATE INDEX IF NOT EXISTS idx_transactions_fingerprint ON transactions(fingerprint);

-- ---------------------------------------------------------------------------
-- MONTHLY SNAPSHOTS (for balances, investment accounts, manual entry)
-- deposits/withdrawals = flows into/out of account
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS monthly_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT NOT NULL,
    account_id TEXT NOT NULL,
    ending_balance REAL NOT NULL,
    deposits REAL DEFAULT 0,
    withdrawals REAL DEFAULT 0,
    FOREIGN KEY (account_id) REFERENCES accounts(account_id),
    UNIQUE(month, account_id)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_month ON monthly_snapshots(month);
CREATE INDEX IF NOT EXISTS idx_snapshots_account ON monthly_snapshots(account_id);
