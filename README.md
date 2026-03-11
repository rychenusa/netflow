# Netflow

Personal finance tracker for monitoring **spending, income, and net worth** using CSV imports.

Netflow is a lightweight dashboard that ingests bank or credit card exports, automatically detects columns, and builds a local financial dataset for analysis and visualization.

Designed to be **local-first, simple, and fast** — no APIs, no external integrations.

**Live demo:**  
https://netflow.streamlit.app/  
Click **Try demo** to explore the dashboard with sample data.

Built by Ryan Chen.

---

## Features

• Import bank or credit card CSV exports (BofA, Amex, Chase, etc.)  
• Automatic column detection and normalization  
• Monthly spending and income analysis  
• Net worth tracking across accounts  
• Investment and alternative asset tracking  
• Transaction categorization rules  
• Fully local data storage (SQLite)

Netflow focuses on **transparent data workflows rather than third-party integrations**, allowing users to maintain full control over their financial data.

---

## Data Model

Netflow tracks two core financial datasets.

**Transactions**

Imported from bank or credit card CSV exports.

Fields include:

- date  
- description  
- amount  
- account  
- category  

Transactions power the spending and income dashboard.

---

**Account Balances**

Manual monthly snapshots used for net worth tracking.

Fields include:

- month (YYYY-MM)  
- account ID  
- account type (cash, debit, credit, investment, alternative, loan)  
- ending balance  
- deposits  
- withdrawals  

Net worth is computed from these snapshots.

---

## Quick Start

Clone the repository and run the dashboard locally.

```bash
git clone https://github.com/rychenusa/netflow.git
cd netflow
pip install -r requirements.txt
streamlit run dashboard/app.py
