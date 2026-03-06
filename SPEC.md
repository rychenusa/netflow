# Netflow — Full Product & Technical Specification

Use this document to recreate the entire Netflow app from scratch. It includes all features and implementation details as of the latest version.

---

## 1. Product specification

### 1.1 Overview

**Netflow** is a local-first personal finance tracker web app. Users can:

- Track **spending and income** by uploading bank or card CSVs (auto-detect columns).
- Track **net worth** by entering account balances (brokerage, bank, crypto, etc.).
- View **summary metrics**, **charts** (net worth, monthly spending, categories, income vs expenses, asset allocation, investment performance), and **manage imports** (list/remove by import ID).
- Use **optional AI** (OpenAI) to suggest categories for “Other” transactions and ask short questions about spending.

Data is stored in SQLite. The app supports **multiple users**: each person signs up or logs in and sees only their own data. A **demo mode** lets visitors try the app with sample data without signing up.

### 1.2 User flows

**Unauthenticated**

- Land on login/signup screen.
- **Try demo**: one click → create/use “demo” user, seed from `data/samples/bofa_sample.csv` and `amex_sample.csv` if empty, log in as demo, show dashboard with banner “You’re viewing the demo” and **← Back to login**.
- **Log in**: username + password (stored lowercase; lookup case-insensitive), bcrypt check → set `user_id` and `username` in session, show dashboard.
- **Sign up**: username (min 2 chars, reserved “demo”) + password → insert into `users` (username lowercase), bcrypt hash → log in and show dashboard.

**Authenticated**

- **Sidebar**: “Logged in as **{username}**” (or “(demo)”); **Log out** (or “Log out (back to login)” in demo).
- **Add Data** (two sections):
  - **Net worth & balances**: manual entry — Month (YYYY-MM), Account ID, Account type (cash/investment/alternative/credit/loan), Ending balance, Deposits, Withdrawals → REPLACE into `monthly_snapshots`; `ensure_account(..., user_id)`.
  - **Spending & income**:  
    - **Import CSV file**: upload CSV → `extract_transaction_section` (multi-section bank CSV support) → `detect_columns` → show file name, row count, column mapping (Date ← …, Description ← …, Amount ← …), optional “Transaction table starts at line X” → account name, account type → preview “First rows we’ll import” → **Import transactions** → `import_from_raw_dataframe(..., user_id=user_id)`.
    - **Paste table**: tab-separated date, description, amount → `import_from_raw_dataframe(..., user_id=user_id)`.
- **View by month**: dropdown “All” or YYYY-MM; filters charts and summary when a month is selected.
- **Manage imports**: expander lists imports (ID, File, Account, Date, Rows); “Import ID to remove” defaults to min existing ID; **Delete this import** → `delete_import(conn, id, user_id)` (only if import belongs to user).
- **Summary**: Total spending (all time or selected month), Total income, Net worth, This month spending (with month label e.g. “March 2026”), This month surplus (delta: Income $X). Caption: net worth from balances; this month = current calendar month. Expander “More numbers”: all-time net cashflow, savings rate.
- **Charts**: Net Worth Over Time (line), Monthly Spending (bar), Spending by Category (donut), Income vs Expenses (grouped bar), Asset Allocation (donut), Investment Performance (table).
- **AI (optional)**: expander; if no API key: input for OpenAI key + **Turn on AI** / **Clear key**. If key set: **Turn off AI**; tabs “Suggest categories” (list “Other” transactions, Suggest → show suggestion → Apply to update category), “Ask about spending” (question + context from totals/top categories → LLM answer).

### 1.3 Data isolation

- Every query scopes by **user_id**: accounts (user_id), transactions/imports/snapshots via account_id ∈ user’s accounts.
- `load_accounts(conn, user_id)`, `load_snapshots(conn, user_id)`, `load_imports(conn, user_id)`, `get_available_months(conn, user_id)`, `monthly_expenses(conn, user_id)`, `monthly_income(conn, user_id)`, `category_spend(conn, user_id, month=…)`, `total_spending(conn, user_id)`, `total_income(conn, user_id)`, `latest_net_worth(conn, user_id)`, `this_month_*`, `net_worth_by_month(conn, user_id)`, `get_other_transactions(conn, user_id)`, `get_distinct_categories(conn, user_id)`, `delete_import(conn, id, user_id)`, `update_transaction_category(conn, txn_id, cat, user_id)`, `investment_performance(conn, user_id)`.
- ETL: `ensure_account(conn, account_id, user_id, ...)`, `import_from_dataframe(..., user_id)`, `import_from_raw_dataframe(..., user_id=user_id)`, `_import_hash_exists(conn, file_hash, user_id)`, `get_existing_fingerprints(conn, user_id=user_id)`.

### 1.4 Branding / credit

- **Title and subtitle**: The product name is **Netflow** with subtitle **Personal Finance Tracker**. Show both in the app and README.
- **In the Streamlit app**:
  - **Title + subtitle**: Where the app shows the main title, use `st.title("Netflow")` followed by `st.caption("Personal Finance Tracker")` in two places: (1) login/signup screen (when not logged in), (2) main dashboard (when logged in).
  - **Credit line**: Show “Built by Ryan Chen” at the **bottom of the page** only, in a subtle style (e.g. centered, muted gray `#71717a`, small font 0.75rem, after a separator). Use one place: end of main content before `conn.close()` when logged in, and just before `st.stop()` on the login/signup screen. Example: `st.markdown('<p style="text-align: center; color: #71717a; font-size: 0.75rem; margin-top: 2rem;">Built by Ryan Chen</p>', unsafe_allow_html=True)`. Do not show in the sidebar.
- **In the README**: Use heading `# Netflow` then a bold subtitle **"Personal Finance Tracker"**, then the short tagline: “Personal finance tracker for monitoring spending, income, and net worth using CSV imports.” Then a line: **“Built by Ryan Chen.”** before the live app link and rest of the doc.

### 1.5 UI/UX requirements

- **Dark theme**: black/dark gray background, light text, blue accent (#3b82f6). Streamlit `base = "dark"`, custom CSS for main area, sidebar, metrics, inputs, buttons, expanders.
- **Charts**: dark-friendly; use **BAR_CHART_LAYOUT** for line/bar charts and **PIE_CHART_LAYOUT** for pie/donut to avoid Plotly TypeError (minimal keys: no full CHART_LAYOUT spread on pie/bar).
- **Copy**: “Sign up or log in”; “Try demo”; “Back to login” when in demo; “We’re importing: …” and “First rows we’ll import” for CSV; “Net worth comes from …” and “This month (March 2026)” in summary.

---

## 2. Technical specification

### 2.1 Stack

- **Runtime**: Python 3.x
- **Backend**: Streamlit (single app, `dashboard/app.py`)
- **Database**: SQLite (`db/finance.db`)
- **Data**: pandas, Plotly (charts)
- **Auth**: bcrypt (password hash)
- **Optional**: OpenAI (openai>=1.0.0) for AI features

**requirements.txt**

```
pandas>=2.0.0
streamlit>=1.29.0
plotly>=5.18.0
PyYAML>=6.0
openai>=1.0.0
bcrypt>=4.0.0
```

### 2.2 Project structure

```
netflow/
├── .streamlit/
│   └── config.toml          # Dark theme, server headless
├── dashboard/
│   ├── app.py               # Single Streamlit app (auth, add data, summary, charts, AI, manage imports)
│   └── llm_helper.py        # get_api_key(), llm_suggest_category(), llm_ask()
├── etl/
│   ├── __init__.py
│   ├── normalize_transactions.py  # extract_transaction_section, normalize_columns, get_column_mapping, detect_columns, normalize_to_canonical
│   ├── categorize.py        # load_rules, categorize_transactions (YAML keywords)
│   ├── dedupe.py            # make_fingerprint, add_fingerprints, filter_new_only, get_existing_fingerprints(conn, user_id=...)
│   └── import_transactions.py # ensure_schema, ensure_account(conn, account_id, user_id, ...), _import_hash_exists(conn, file_hash, user_id), _next_import_id, _create_import_record, import_from_dataframe(..., user_id), import_from_raw_dataframe(..., user_id=...)
├── models/
│   └── schema.sql           # users, accounts(user_id), imports, transactions, monthly_snapshots
├── rules/
│   └── category_rules.yaml  # category: [KEYWORD1, KEYWORD2, ...]
├── data/
│   ├── samples/             # bofa_sample.csv, amex_sample.csv (committed)
│   └── raw/                 # gitignored
├── db/
│   └── finance.db           # created at runtime; gitignored
├── SPEC.md                  # This document
└── README.md
```

### 2.3 Database schema (SQLite)

**users**

- `user_id` INTEGER PRIMARY KEY AUTOINCREMENT
- `username` TEXT NOT NULL UNIQUE
- `password_hash` TEXT NOT NULL
- `created_at` TEXT NOT NULL DEFAULT (datetime('now'))
- Index: `idx_users_username`

**accounts**

- `account_id` TEXT PRIMARY KEY
- `user_id` INTEGER NOT NULL REFERENCES users(user_id)
- `account_name` TEXT, `account_type` TEXT NOT NULL, `institution` TEXT
- Index: `idx_accounts_user` (created in migration, not in schema.sql to avoid error on existing DBs)

**imports**

- `import_id` INTEGER PRIMARY KEY AUTOINCREMENT (assign explicitly: reuse smallest available ID after deletes)
- `file_name` TEXT, `account_id` TEXT, `import_date` TEXT, `row_count` INTEGER, `file_hash` TEXT UNIQUE
- Indexes: `idx_imports_file_hash`, `idx_imports_account`

**transactions**

- `txn_id` INTEGER PRIMARY KEY AUTOINCREMENT
- `date_posted` TEXT NOT NULL, `account_id` TEXT NOT NULL, `description` TEXT, `merchant` TEXT, `category` TEXT, `txn_type` TEXT NOT NULL, `amount` REAL NOT NULL, `fingerprint` TEXT UNIQUE NOT NULL, `import_id` INTEGER
- Indexes: date, account, category, fingerprint

**monthly_snapshots**

- `snapshot_id` INTEGER PRIMARY KEY AUTOINCREMENT
- `month` TEXT NOT NULL, `account_id` TEXT NOT NULL, `ending_balance` REAL NOT NULL, `deposits` REAL DEFAULT 0, `withdrawals` REAL DEFAULT 0
- UNIQUE(month, account_id); indexes on month, account_id

**Migrations (in ensure_schema)**

- Add `import_id` to transactions if missing.
- Add `user_id` to accounts if missing; create default user (username “default”, password hash “default”); UPDATE accounts SET user_id = 1 WHERE user_id IS NULL; CREATE INDEX IF NOT EXISTS idx_accounts_user ON accounts(user_id).

### 2.4 ETL pipeline

**CSV → DB (per user)**

1. **extract_transaction_section(file_or_path, encoding)**  
   Read file as text; find first line with “date” and (“description” or “amount”); from that line to end parse as CSV; drop summary rows (Beginning balance, Total credits, etc.); return `(df, meta)` with meta: `header_line_1based`, `file_lines`, `columns_in_file`. If no header found return `(empty DataFrame, None)`.

2. **normalize_columns(df)**  
   Lowercase/strip column names; map to date, description, amount via aliases (including “unnamed”, “summary amt”, debit/credit → amount = credit - debit); output columns: date, description, amount.

3. **get_column_mapping(df)**  
   Same alias logic; return `{"date": "…", "description": "…", "amount": "…"}` for UI.

4. **detect_columns(df)**  
   Run normalize_columns; require date and amount; return `{ok, message, canonical_columns}`.

5. **normalize_to_canonical(df, account_id)**  
   Normalize columns; parse date to YYYY-MM-DD; set date_posted, account_id, description, merchant, category (from categorize), txn_type, amount.

6. **categorize_transactions(df, rules_path)**  
   Load `rules/category_rules.yaml` (category → list of uppercase keywords); match description (uppercased) to first keyword; default “Other”.

7. **add_fingerprints(df)**  
   fingerprint = SHA256(date_posted|account_id|description|amount).

8. **get_existing_fingerprints(conn, user_id=user_id)**  
   SELECT fingerprint FROM transactions t JOIN accounts a ON t.account_id = a.account_id AND a.user_id = ?.

9. **filter_new_only(df, existing_fingerprints)**  
   Drop rows whose fingerprint is in set.

10. **import_from_dataframe(df, account_id, conn, user_id, ...)**  
    If file_hash already exists for this user → skip. ensure_account(conn, account_id, user_id, ...). normalize_to_canonical → categorize → add_fingerprints → filter_new_only → _create_import_record(import_id, file_name, account_id, row_count, file_hash) with import_id = _next_import_id(conn). Insert new rows into transactions with import_id.

**_next_import_id(conn)**  
Return smallest integer k ≥ 1 not in SELECT import_id FROM imports (reuse IDs after delete).

### 2.5 Streamlit app layout (order)

1. **set_page_config** (title Netflow, wide).
2. **Custom CSS** (dark background, metrics, sidebar, inputs, buttons, expanders).
3. **CHART_LAYOUT**, **PIE_CHART_LAYOUT**, **BAR_CHART_LAYOUT** (minimal for pie/bar to avoid TypeError).
4. **Auth**: if no user_id → login/signup + Try demo; else → main app.
5. **Login screen**: `st.title("Netflow")`, `st.caption("Personal Finance Tracker")`, then sign-up/login copy and tabs; at bottom of login content, separator then subtle “Built by Ryan Chen” (centered, muted, small); then `st.stop()`.
6. **Demo banner** (if is_demo): info + “← Back to login” button.
7. **Main title**: `st.title("Netflow")`, `st.caption("Personal Finance Tracker")`.
8. **Sidebar**: “Logged in as **username**” + Log out.
9. **Expandable “What is this?”** (quick start, two sections Add Data).
10. **Add Data** header; radio “Net worth & balances” | “Spending & income”; then either manual balance form or CSV/paste with account name and type.
11. **View by month** dropdown (All + get_available_months(conn, user_id)).
12. **Manage imports** expander (table, Import ID to remove default min, Delete).
13. **AI (optional)** expander (key input if no key; Suggest categories / Ask about spending if key set).
14. **Summary** header; metrics (Total spending, Total income, Net worth, This month spending, This month surplus); caption; “More numbers” expander.
15. **Net Worth Over Time** (line, BAR_CHART_LAYOUT).
16. **Monthly Spending** (bar, BAR_CHART_LAYOUT).
17. **Spending by Category** (pie/donut, PIE_CHART_LAYOUT + legend).
18. **Income vs Expenses** (grouped bar, BAR_CHART_LAYOUT).
19. **Asset Allocation** (pie/donut, PIE_CHART_LAYOUT + legend).
20. **Investment Performance** (dataframe).
21. **Footer**: separator then subtle “Built by Ryan Chen” (centered, muted gray, small font) at bottom of page.
22. conn.close().

### 2.6 Theme and charts

**.streamlit/config.toml**

```toml
[theme]
base = "dark"
primaryColor = "#3b82f6"
backgroundColor = "#0a0a0a"
secondaryBackgroundColor = "#171717"
textColor = "#fafafa"
font = "sans serif"

[server]
headless = true
```

**Custom CSS (snippet)**  
- .stApp: background linear-gradient #0a0a0a → #0f0f0f.  
- .block-container: padding, max-width 1400px.  
- h1/h2/h3: color #fafafa.  
- stMetricValue: color #3b82f6; stMetricLabel: #a1a1aa.  
- Sidebar: background #0a0a0a, border #262626.  
- Inputs: background #171717, border #262626, color #fafafa.  
- Buttons: border-radius 8px; hover lift and blue shadow.  
- Expanders/alerts: dark bg, border #262626.

**PIE_CHART_LAYOUT** (for pie/donut only)  
- font (family, size, color #e4e4e7), paper_bgcolor, plot_bgcolor, margin, hoverlabel. No xaxis/yaxis/title/legend/colorway to avoid TypeError.

**BAR_CHART_LAYOUT** (for line/bar)  
- font, paper_bgcolor, plot_bgcolor, margin, xaxis (showgrid, gridcolor, zeroline=False), yaxis same, hoverlabel, legend. No title dict.

**CHART_LAYOUT**  
- Full definition for colorway and reference; do not spread full CHART_LAYOUT on pie or bar charts in update_layout (use PIE_CHART_LAYOUT / BAR_CHART_LAYOUT).

### 2.7 ETL loading (Streamlit Cloud–safe)

- Load ETL by file path (importlib.util) so it works when `import etl` fails.  
- Order: normalize_transactions, categorize, dedupe, import_transactions.  
- Expose: detect_columns, extract_transaction_section, get_column_mapping, normalize_to_canonical, import_from_raw_dataframe, ensure_schema, ensure_account.

### 2.8 AI (optional)

- **llm_helper.get_api_key()**: session_state openai_api_key > Streamlit secrets OPENAI_API_KEY > env OPENAI_API_KEY.
- **Turn on AI**: store key in session_state from password input; **Turn off AI** clears it.
- **llm_suggest_category(description, existing_categories)**: OpenAI gpt-4o-mini, system prompt to pick one category; return category or None.
- **llm_ask(question, context)**: same model, answer in 1–3 sentences from context.

### 2.9 Sample data (demo)

- **bofa_sample.csv**: Date, Description, Amount, Debit, Credit (BofA-style).  
- **amex_sample.csv**: Date, Description, Amount (single amount column).  
- _seed_demo_data(demo_user_id): if transaction count for user is 0, run import_from_raw_dataframe for each sample file with that user_id and account_id bofa_demo/amex_demo.

### 2.10 Deployment

- **Streamlit Community Cloud**: connect GitHub repo, main file `dashboard/app.py`, branch main. Each deployment has its own SQLite DB.  
- **Local**: `streamlit run dashboard/app.py` from project root; DB at `db/finance.db`.

---

## 3. Implementation checklist (recreate app)

- [ ] Create project layout (dashboard/, etl/, models/, rules/, data/samples/, db/, .streamlit/).
- [ ] requirements.txt (pandas, streamlit, plotly, PyYAML, openai, bcrypt).
- [ ] models/schema.sql (users, accounts without idx_accounts_user, imports, transactions, monthly_snapshots).
- [ ] etl/normalize_transactions.py (aliases, extract_transaction_section → (df, meta), normalize_columns, get_column_mapping, detect_columns, normalize_to_canonical, SUMMARY_ROW_MARKERS).
- [ ] etl/categorize.py (load_rules from YAML, categorize_transactions).
- [ ] etl/dedupe.py (make_fingerprint, add_fingerprints, filter_new_only, get_existing_fingerprints with optional user_id).
- [ ] etl/import_transactions.py (ensure_schema with migrations for import_id and user_id and idx_accounts_user, ensure_account with user_id, _import_hash_exists with user_id, _next_import_id, _create_import_record with explicit import_id, import_from_dataframe with user_id, import_from_raw_dataframe with user_id).
- [ ] rules/category_rules.yaml (groceries, dining, transport, subscriptions, utilities, shopping, entertainment, other).
- [ ] data/samples: bofa_sample.csv, amex_sample.csv.
- [ ] .streamlit/config.toml (dark theme).
- [ ] dashboard/llm_helper.py (get_api_key, llm_suggest_category, llm_ask).
- [ ] dashboard/app.py: ETL load by path; DB_PATH; slugify_account; get_conn; all data helpers with user_id; auth (_auth_conn, _check_password, Try demo, _ensure_demo_user, _seed_demo_data, login, signup); demo banner + Back to login; title + subtitle (st.title("Netflow"), st.caption("Personal Finance Tracker") on login screen and main dashboard); subtle “Built by Ryan Chen” footer at bottom of page only (and at bottom of login screen before st.stop()); Add Data (two sections, CSV with column mapping and preview); View by month; Manage imports (default ID min, delete_import with user_id); AI expander (key in app, suggest/ask); Summary (metrics, caption, More numbers); charts (Net worth line, Monthly spending bar, Category pie, Income vs expenses bar, Asset allocation pie, Investment perf table) using BAR_CHART_LAYOUT and PIE_CHART_LAYOUT only; custom CSS.
- [ ] README.md: # Netflow, bold subtitle "Personal Finance Tracker", tagline, "Built by Ryan Chen.", quick start, two sections, demo, security, deploy, tech.

---

*End of Netflow Product & Technical Specification. Use this to rebuild the app from scratch including all updated behavior (per-user auth, demo, dark UI, minimal chart layouts, import ID reuse, column mapping display, and AI key in-app).*
