"""
Netflow - Streamlit Dashboard.
Run from project root: streamlit run dashboard/app.py
"""

import os
import re
import sys
import sqlite3
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from io import StringIO

# Project root (parent of dashboard/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
DB_PATH = os.path.join(PROJECT_ROOT, "db", "finance.db")

# Account type groupings for net worth
ASSET_TYPES = {"cash", "investment", "alternative"}
LIABILITY_TYPES = {"credit", "loan"}


def slugify_account(name: str) -> str:
    """Turn 'BofA Checking' or 'bofa_jan24.csv' into 'bofa_checking' or 'bofa_jan24'."""
    if not name or not str(name).strip():
        return "account"
    s = str(name).strip()
    s = re.sub(r"\.csv$", "", s, flags=re.I)
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[-\s]+", "_", s)
    return s.lower() or "account"


def get_conn():
    """Return a DB connection; ensure schema exists."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    from etl.import_transactions import ensure_schema
    conn = sqlite3.connect(DB_PATH)
    ensure_schema(conn)
    return conn


def load_transactions(conn) -> pd.DataFrame:
    return pd.read_sql(
        "SELECT * FROM transactions ORDER BY date_posted",
        conn,
        parse_dates=["date_posted"],
    )


def load_accounts(conn) -> pd.DataFrame:
    return pd.read_sql("SELECT * FROM accounts", conn)


def load_snapshots(conn) -> pd.DataFrame:
    return pd.read_sql("SELECT * FROM monthly_snapshots ORDER BY month", conn)


def monthly_expenses(conn) -> pd.DataFrame:
    """Sum of amount < 0 where txn_type != 'transfer', by month."""
    df = pd.read_sql("""
        SELECT date_posted, amount, txn_type
        FROM transactions
        WHERE amount < 0 AND (txn_type IS NULL OR txn_type != 'transfer')
    """, conn)
    if df.empty:
        return pd.DataFrame(columns=["month", "expenses"])
    df["month"] = pd.to_datetime(df["date_posted"]).dt.to_period("M").astype(str)
    return df.groupby("month", as_index=False)["amount"].sum().rename(columns={"amount": "expenses"})


def monthly_income(conn) -> pd.DataFrame:
    """Sum of amount > 0 where txn_type NOT IN ('refund','transfer'), by month."""
    df = pd.read_sql("""
        SELECT date_posted, amount, txn_type
        FROM transactions
        WHERE amount > 0 AND (txn_type IS NULL OR txn_type NOT IN ('refund', 'transfer'))
    """, conn)
    if df.empty:
        return pd.DataFrame(columns=["month", "income"])
    df["month"] = pd.to_datetime(df["date_posted"]).dt.to_period("M").astype(str)
    return df.groupby("month", as_index=False)["amount"].sum().rename(columns={"amount": "income"})


def net_worth_by_month(conn) -> pd.DataFrame:
    """For each month: assets (cash+investment+alternative) - liabilities (credit+loan)."""
    snap = load_snapshots(conn)
    acct = load_accounts(conn)
    if snap.empty or acct.empty:
        return pd.DataFrame(columns=["month", "assets", "liabilities", "net_worth"])
    merge = snap.merge(acct[["account_id", "account_type"]], on="account_id")
    merge["is_asset"] = merge["account_type"].isin(ASSET_TYPES)
    merge["is_liability"] = merge["account_type"].isin(LIABILITY_TYPES)
    merge_asset = merge[merge["is_asset"]].groupby("month")["ending_balance"].sum().reset_index(name="assets")
    merge_liab = merge[merge["is_liability"]].groupby("month")["ending_balance"].sum().reset_index(name="liabilities")
    by_month = merge_asset.merge(merge_liab, on="month", how="outer").fillna(0)
    by_month["net_worth"] = by_month["assets"] - by_month["liabilities"]
    return by_month.sort_values("month")


def category_spend(conn) -> pd.DataFrame:
    """Total spending by category (amount < 0, exclude transfer)."""
    df = pd.read_sql("""
        SELECT category, SUM(amount) AS total
        FROM transactions
        WHERE amount < 0 AND (txn_type IS NULL OR txn_type != 'transfer')
        GROUP BY category
    """, conn)
    return df


def investment_performance(conn) -> pd.DataFrame:
    """Per account (investment type): P&L and return % by month.
    P&L = B1 - B0 - D + W; return_pct = P&L / (B0 + D/2 - W/2)
    """
    snap = load_snapshots(conn)
    acct = load_accounts(conn)
    inv_accounts = acct[acct["account_type"] == "investment"]["account_id"].tolist()
    if not inv_accounts or snap.empty:
        return pd.DataFrame(columns=["account_id", "month", "pnl", "return_pct"])
    snap = snap[snap["account_id"].isin(inv_accounts)].sort_values(["account_id", "month"])
    rows = []
    for aid, grp in snap.groupby("account_id"):
        grp = grp.sort_values("month")
        prev_balance = None
        for _, row in grp.iterrows():
            B1 = row["ending_balance"]
            D = row.get("deposits") or 0
            W = row.get("withdrawals") or 0
            B0 = prev_balance if prev_balance is not None else B1 - D + W  # assume first month no prior
            pnl = B1 - B0 - D + W
            denom = B0 + D / 2 - W / 2
            return_pct = (pnl / denom * 100) if denom and denom != 0 else None
            rows.append({"account_id": aid, "month": row["month"], "pnl": pnl, "return_pct": return_pct})
            prev_balance = B1
    return pd.DataFrame(rows)


def cashflow_and_valuation(conn) -> pd.DataFrame:
    """cashflow_surplus = income - expenses; net_worth_change; valuation_change."""
    exp = monthly_expenses(conn)
    inc = monthly_income(conn)
    nw = net_worth_by_month(conn)
    if exp.empty and inc.empty:
        return pd.DataFrame(columns=["month", "cashflow_surplus", "net_worth_change", "valuation_change"])
    m = exp.merge(inc, on="month", how="outer").fillna(0)
    m["cashflow_surplus"] = m["income"] - m["expenses"].abs()
    m = m.merge(nw[["month", "net_worth"]], on="month", how="outer").sort_values("month")
    m["net_worth_change"] = m["net_worth"].diff()
    m["valuation_change"] = m["net_worth_change"] - m["cashflow_surplus"]
    return m


# --------------- UI ---------------

st.set_page_config(page_title="Netflow", layout="wide")
st.title("Netflow")

conn = get_conn()

# --------------- Input methods ---------------
st.header("Add Data")

input_method = st.radio(
    "Input method",
    ["Upload CSV (auto-detect)", "Paste table (tab-separated)", "Manual balance entry"],
    horizontal=True,
)

if input_method == "Upload CSV (auto-detect)":
    uploaded = st.file_uploader(
        "Upload your bank or card CSV — we'll detect columns automatically",
        type=["csv"],
        help="Supports BofA, Amex, and most CSVs with date, description, and amount (or debit/credit).",
    )
    if uploaded:
        try:
            df = pd.read_csv(uploaded, on_bad_lines="skip", encoding="utf-8")
        except Exception:
            df = pd.read_csv(uploaded, on_bad_lines="skip", encoding="latin-1")
        from etl.normalize_transactions import detect_columns
        from etl.import_transactions import import_from_raw_dataframe

        detection = detect_columns(df)
        if detection["ok"]:
            st.success(detection["message"])
            default_name = slugify_account(uploaded.name).replace("_", " ").title()
            account_name = st.text_input(
                "Account name (e.g. BofA Checking, Amex Gold)",
                value=default_name,
                placeholder="Give this account a name",
            )
            account_id = slugify_account(account_name) if account_name else slugify_account(uploaded.name)
            account_type = st.selectbox(
                "Account type",
                ["cash", "credit", "investment", "alternative", "loan"],
                index=0,
                help="Checking/savings = cash, credit card = credit, brokerage/crypto = investment.",
            )
            with st.expander("Preview first 5 rows"):
                try:
                    from etl.normalize_transactions import normalize_to_canonical
                    preview = normalize_to_canonical(df.head(10), account_id=account_id)
                    st.dataframe(preview, use_container_width=True)
                except Exception as e:
                    st.caption(str(e))
            if st.button("Import transactions", type="primary"):
                n = import_from_raw_dataframe(
                    df, account_id, db_path=DB_PATH,
                    account_name=account_name or account_id,
                    account_type=account_type,
                    file_name=uploaded.name,
                )
                st.success(f"Imported {n} new transactions. Your dashboard will update below.")
                st.rerun()
        else:
            st.warning(detection["message"])
            st.caption("Your file columns: " + ", ".join(str(c) for c in df.columns))

elif input_method == "Paste table (tab-separated)":
    paste = st.text_area("Paste rows: date, description, amount (tab-separated)", height=120)
    account_id_paste = st.text_input("Account ID (paste)", value="bofa_checking")
    if paste and account_id_paste:
        try:
            df = pd.read_csv(StringIO(paste), sep="\t", header=None, names=["date", "description", "amount"])
            from etl.import_transactions import import_from_raw_dataframe
            n = import_from_raw_dataframe(df, account_id_paste, db_path=DB_PATH)
            st.success(f"Imported {n} new transactions.")
        except Exception as e:
            st.error(str(e))

else:
    # Manual balance entry
    month_manual = st.text_input("Month (YYYY-MM)", placeholder="2024-01")
    account_id_manual = st.text_input("Account ID (manual)", placeholder="brokerage")
    account_type_manual = st.selectbox("Account type (manual)", ["cash", "investment", "alternative", "credit", "loan"], index=1)
    ending = st.number_input("Ending balance", value=0.0, step=100.0)
    deposits = st.number_input("Deposits", value=0.0, step=100.0)
    withdrawals = st.number_input("Withdrawals", value=0.0, step=100.0)
    if st.button("Save snapshot") and month_manual and account_id_manual:
        from etl.import_transactions import ensure_schema, ensure_account
        ensure_schema(conn)
        ensure_account(conn, account_id_manual, account_type=account_type_manual)
        conn.execute(
            "REPLACE INTO monthly_snapshots (month, account_id, ending_balance, deposits, withdrawals) VALUES (?, ?, ?, ?, ?)",
            (month_manual, account_id_manual, ending, deposits, withdrawals),
        )
        conn.commit()
        st.success("Saved.")

conn = get_conn()  # refresh after possible writes

# --------------- Net Worth Chart ---------------
st.header("Net Worth Over Time")
nw_df = net_worth_by_month(conn)
if not nw_df.empty:
    fig = px.line(nw_df, x="month", y="net_worth", title="Net Worth")
    fig.update_layout(xaxis_title="Month", yaxis_title="Net Worth")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Add monthly snapshots (manual balance entry) to see net worth.")

# --------------- Monthly Spending ---------------
st.header("Monthly Spending")
exp_df = monthly_expenses(conn)
if not exp_df.empty:
    exp_df["expenses"] = exp_df["expenses"].abs()
    fig = px.bar(exp_df, x="month", y="expenses", title="Monthly Expenses")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Import transactions to see monthly spending.")

# --------------- Spending Categories ---------------
st.header("Spending by Category")
cat_df = category_spend(conn)
if not cat_df.empty:
    cat_df["total"] = cat_df["total"].abs()
    total_spend = cat_df["total"].sum()
    cat_df["pct"] = (cat_df["total"] / total_spend * 100).round(1)
    fig = px.pie(cat_df, values="total", names="category", title="Spending by Category (%)")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Import transactions to see category breakdown.")

# --------------- Income vs Expenses ---------------
st.header("Income vs Expenses")
inc_df = monthly_income(conn)
if not exp_df.empty or not inc_df.empty:
    m = exp_df.merge(inc_df, on="month", how="outer").fillna(0)
    m["expenses"] = m["expenses"].abs()
    fig = go.Figure(data=[
        go.Bar(name="Income", x=m["month"], y=m["income"]),
        go.Bar(name="Expenses", x=m["month"], y=m["expenses"]),
    ])
    fig.update_layout(barmode="group", title="Income vs Expenses", xaxis_title="Month")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Import transactions to see income vs expenses.")

# --------------- Asset Allocation ---------------
st.header("Asset Allocation")
nw_df = net_worth_by_month(conn)
snap = load_snapshots(conn)
acct = load_accounts(conn)
if not snap.empty and not acct.empty:
    merge = snap.merge(acct, on="account_id")
    asset_only = merge[merge["account_type"].isin(ASSET_TYPES)]
    # Use latest month per account for allocation
    latest = asset_only.sort_values("month").groupby("account_id").last().reset_index()
    total_assets = latest["ending_balance"].sum()
    if total_assets > 0:
        latest["pct"] = (latest["ending_balance"] / total_assets * 100).round(1)
        latest = latest.copy()
        latest["label"] = latest["account_name"].fillna(latest["account_id"])
        fig = px.pie(latest, values="ending_balance", names="label", title="Net Worth by Account (%)")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No positive asset balances.")
else:
    st.info("Add monthly snapshots for asset allocation.")

# --------------- Investment Performance ---------------
st.header("Investment Performance")
perf = investment_performance(conn)
if not perf.empty:
    st.dataframe(perf.style.format({"pnl": "${:.2f}", "return_pct": "{:.2f}%"}), use_container_width=True)
else:
    st.info("Add investment account snapshots (manual entry) to see performance.")

conn.close()
