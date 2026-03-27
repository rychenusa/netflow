# Netflow

**Personal Finance Tracker**

Netflow helps you track spending, income, and net worth. Import bank or card CSVs (the app picks out date, description, and amount for you), or enter monthly balances for brokerage, crypto, and other accounts.

**Built by Ryan Chen.**

**Live demo:** [netflow.streamlit.app](https://netflow.streamlit.app/) — open **Try demo** to look around with sample data. The hosted site is for trying the app; use your own copy for records you care about.

[![GitHub](https://img.shields.io/badge/GitHub-rychenusa%2Fnetflow-blue)](https://github.com/rychenusa/netflow)

---

## Run it on your computer

```bash
git clone https://github.com/rychenusa/netflow.git
cd netflow
pip install -r requirements.txt
streamlit run dashboard/app.py
```

Open the URL Streamlit shows (often `http://localhost:8501`). Sign up with a username and password, then add your data.

**Your database** is a single file: `db/finance.db` in the project folder. Copy that file to back up your data. To move to another computer, put `db/finance.db` in the `db/` folder on the new machine and run the app again.

---

## What you can do

**Spending and income** — Upload a CSV or paste rows (date, description, amount). Duplicate uploads of the same file are skipped for your account.

**Net worth** — Enter balances by month and account type (cash, debit, credit, investment, and others). Summary and charts use these numbers.

Example files are in `data/samples/` if you want to test an import first.

---

## Hosted app vs. local

The public Streamlit deployment may reset its database when the app restarts or redeploys. For finances you want to keep, run Netflow locally so `db/finance.db` stays on your machine. You can also self-host and use an external database later if you need to.

---

## Accounts and privacy

Each user only sees their own data. Passwords are stored with bcrypt (hashed), not as plain text.

---

## Project layout

| Path | Role |
|------|------|
| `dashboard/app.py` | Main app |
| `etl/` | CSV import and cleanup |
| `models/schema.sql` | Database layout |
| `rules/category_rules.yaml` | Category keywords |
| `db/finance.db` | Your data (created on first run; not in git) |
| `data/samples/` | Example CSVs |

---

## Tech

Python, SQLite, pandas, Streamlit, Plotly. No paid APIs required to run locally.
