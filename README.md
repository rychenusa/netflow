# Netflow

**Local-first** personal finance tracker: expenses by month, income, spending categories, net worth, account balances, and investment performance. Upload your bank or card CSV and the app **auto-detects columns** — no setup required. Optional manual entry for brokerage, crypto (Coinbase), or prediction markets (Kalshi).

**Live app:** [https://netflow.streamlit.app/](https://netflow.streamlit.app/)

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

## Try it with sample data

Example CSVs are in `data/samples/`:

- `bofa_sample.csv` – checking (debit/credit columns)
- `amex_sample.csv` – card (single amount column)

Upload either file in the app to see the dashboard populate.

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

Each deployment has its own SQLite DB. Anyone with the link can use the app; add auth if you want to restrict access.

---

## Share locally

Anyone can clone the repo and run the app on their machine — data stays in their local `db/finance.db`.

---

## Tech

Python, SQLite, pandas, Streamlit, Plotly. No API keys, runs 100% local and free.
