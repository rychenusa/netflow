# Netflow

**Local-first** personal finance tracker: expenses by month, income, spending categories, net worth, account balances, and investment performance. Upload your bank or card CSV and the app **auto-detects columns** — no setup required. Optional manual entry for brokerage, crypto (Coinbase), or prediction markets (Kalshi).

[![GitHub](https://img.shields.io/badge/GitHub-rychenusa%2Fnetflow-blue)](https://github.com/rychenusa/netflow)

---

## Quick start

```bash
git clone https://github.com/rychenusa/netflow.git
cd netflow
pip install -r requirements.txt
streamlit run dashboard/app.py
```

Open the app in your browser. Under **Add Data** choose **Upload CSV (auto-detect)**, pick a file — we detect date, description, and amount (or debit/credit) automatically. Give the account a name and click **Import transactions**. Done.

---

## How it works

1. **Upload CSV** – Drag and drop your bank or card export. The app detects columns (BofA, Amex, Chase, etc.) and shows a preview. Name the account and import. Duplicates are skipped.
2. **Paste table** – Tab-separated: date, description, amount.
3. **Manual balance** – For accounts that don’t export CSV (brokerage, crypto, Kalshi): enter month, ending balance, deposits, withdrawals.

Your data stays in `db/finance.db` on your machine. No cloud, no account required.

---

## Push this repo to GitHub (first-time setup)

**1. Create the repo on GitHub** (one-time):

- Go to [github.com/new](https://github.com/new)
- Repository name: **netflow**
- Leave "Add a README" **unchecked** (you already have one)
- Click **Create repository**

**2. Push your local code:**

```bash
cd "c:\Users\ryche\OneDrive\Desktop\Cursor Projects\netflow"
git push -u origin main
```

(If `git remote add origin` wasn’t run yet: `git remote add origin https://github.com/rychenusa/netflow.git` then push.)

If the repo **already exists** on GitHub with a README and you need to merge:

```bash
git remote add origin https://github.com/rychenusa/netflow.git
git pull origin main --allow-unrelated-histories
# resolve any conflicts, then:
git push -u origin main
```

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
4. Click **Deploy**. You’ll get a public URL (e.g. `https://netflow-xxx.streamlit.app`).

Each deployment has its own SQLite DB. Anyone with the link can use the app; add auth if you want to restrict access.

---

## Share locally

Anyone can clone the repo and run the app on their machine — data stays in their local `db/finance.db`.

---

## Tech

Python, SQLite, pandas, Streamlit, Plotly. No API keys, runs 100% local and free.
