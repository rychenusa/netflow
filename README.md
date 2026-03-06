# Netflow

**Personal Finance Tracker**

Personal finance tracker for monitoring spending, income, and net worth using CSV imports. Local-first: expenses by month, spending categories, account balances, and investment performance. Upload your bank or card CSV and the app **auto-detects columns** — no setup required. Optional manual entry for brokerage, crypto (Coinbase), or prediction markets (Kalshi).

**Built by Ryan Chen.**

**Live app:** [https://netflow.streamlit.app/](https://netflow.streamlit.app/) — click **Try demo** to explore with sample data (no sign-up).

[![GitHub](https://img.shields.io/badge/GitHub-rychenusa%2Fnetflow-blue)](https://github.com/rychenusa/netflow)

---

## Quick start

```bash
git clone https://github.com/rychenusa/netflow.git
cd netflow
pip install -r requirements.txt
streamlit run dashboard/app.py
```

Open the app in your browser. **Add Data** has two sections:

- **Spending & income** — Import your **credit card** or **debit card** CSV (we auto-detect date, description, amount). Choose *Import CSV file*, pick a file, name the account, and click *Import transactions*. Or paste a tab-separated table (date, description, amount).
- **Net worth & balances** — For brokerage, bank, crypto (e.g. Coinbase), or Kalshi: enter month, account, ending balance, deposits, and withdrawals. Summary **Net worth** is computed from these snapshots only.

---

## How it works

**Add Data** is split into two sections:

1. **Net worth & balances** – Manual balance entry: month (YYYY-MM), account ID, account type, ending balance, deposits, withdrawals. Use this for brokerage, bank, crypto, or prediction markets. Net worth on the Summary and the net worth chart come from these snapshots only.
2. **Spending & income** – **Import CSV file**: drag and drop your bank or card export; we detect columns (BofA, Amex, Chase, etc.) and show a preview. Name the account and import; duplicates are skipped. **Paste table**: tab-separated date, description, amount.

Your data stays in `db/finance.db` on your machine. No cloud, no account required.

---

## Try the demo

On the [live app](https://netflow.streamlit.app/), click **Try demo** to see the dashboard with sample spending and income—no sign-up required. Sign up when you're ready to save your own data.

Example CSVs are also in `data/samples/` (`bofa_sample.csv`, `amex_sample.csv`) to upload in your own account.

---

## Project structure

| Path | Purpose |
|------|--------|
| `dashboard/app.py` | Streamlit UI (upload, charts, manual entry) |
| `etl/` | Import, normalize, categorize, dedupe |
| `models/schema.sql` | SQLite schema |
| `rules/category_rules.yaml` | Spending category keywords |
| `db/finance.db` | Your data (created on first run; not committed) |
| `data/raw/` | Your CSVs (gitignored) |
| `data/samples/` | Example CSVs (committed) |

---

## Deploy online (Streamlit Community Cloud)

**Use Streamlit Community Cloud** — it’s free and built for Streamlit. Vercel and similar platforms are for static/Node apps and don’t run long‑running Python servers, so they’re not suitable for this app.

1. Push this repo to GitHub (see **Push this repo to GitHub** above).
2. Go to **[share.streamlit.io](https://share.streamlit.io)** and sign in with GitHub.
3. Click **New app**, then:
   - **Repository:** `rychenusa/netflow`
   - **Branch:** `main`
   - **Main file path:** `dashboard/app.py`
4. Click **Deploy**. You’ll get a public URL — this repo is live at **[https://netflow.streamlit.app/](https://netflow.streamlit.app/)**.

Each deployment has its own SQLite DB.

---

## Security (private for each person)

**Each person has their own account.** Sign up with a username and password; your data (imports, transactions, balances) is stored under your account and **no one else can see it**. Good for sharing the app link with friends—each friend signs up and only sees their own data.

- **Passwords** are hashed with bcrypt; we never store plain text.
- **Optional extra layers** if you need them: use a strong password, don’t share your login, and if you deploy elsewhere you can add a reverse proxy with extra auth (e.g. OAuth/Clerk in front of the app) or run the app on a private URL.

---

## Share locally

Anyone can clone the repo and run the app on their machine — data stays in their local `db/finance.db`.

---

## Tech

Python, SQLite, pandas, Streamlit, Plotly. No API keys, runs 100% local and free.
