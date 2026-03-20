# Netflow

Personal finance ETL pipeline for tracking **spending, income, and net worth** from CSV exports.

Netflow ingests bank or credit card data, standardizes schemas across institutions, and builds a structured dataset for analysis and visualization. Designed to be **local-first, simple, and fast**.

**Live demo:**  
https://netflow.streamlit.app/  
*(Demo only — run locally for real data)*

Built by Ryan Chen.

---

## Features

• CSV ingestion (BofA, Amex, Chase, etc.)  
• Automatic schema detection and normalization  
• SQLite-backed data model (transactions + balances)  
• Categorization and aggregation pipeline  
• Monthly spending, income, and net worth tracking  
• Streamlit dashboard for visualization  

---

## Data Model

### Transactions

- date  
- description  
- amount  
- account  
- category  

---

### Account Balances

- month (YYYY-MM)  
- account_id  
- account_type (cash, debit, credit, investment, alternative, loan)  
- ending_balance  
- deposits  
- withdrawals  

---

## Quick Start

```bash
git clone https://github.com/rychenusa/netflow.git
cd netflow
pip install -r requirements.txt
streamlit run dashboard/app.py
