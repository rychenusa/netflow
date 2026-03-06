"""
Netflow - Streamlit Dashboard.
Run from project root: streamlit run dashboard/app.py
"""

import os
import re
import sys
import sqlite3
from datetime import datetime
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from io import StringIO
from typing import Optional

# Project root (parent of dashboard/) — ensure imports work on Streamlit Cloud
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(_APP_DIR)
for _path in (PROJECT_ROOT, _APP_DIR, os.getcwd(), os.path.dirname(os.getcwd())):
    if _path and _path not in sys.path:
        sys.path.insert(0, _path)
DB_PATH = os.path.join(PROJECT_ROOT, "db", "finance.db")

# Load ETL modules by file path (works on Streamlit Cloud when "import etl" fails)
def _load_etl():
    import importlib.util
    import types
    etl_dir = os.path.join(PROJECT_ROOT, "etl")
    norm_path = os.path.join(etl_dir, "normalize_transactions.py")
    cat_path = os.path.join(etl_dir, "categorize.py")
    dedupe_path = os.path.join(etl_dir, "dedupe.py")
    imp_path = os.path.join(etl_dir, "import_transactions.py")
    out = {}
    if not all(os.path.isfile(p) for p in (norm_path, cat_path, dedupe_path, imp_path)):
        return out
    if "etl" not in sys.modules:
        sys.modules["etl"] = types.ModuleType("etl")
    # Load in dependency order: normalize_transactions, categorize, dedupe, import_transactions
    for name, path in (
        ("etl.normalize_transactions", norm_path),
        ("etl.categorize", cat_path),
        ("etl.dedupe", dedupe_path),
        ("etl.import_transactions", imp_path),
    ):
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        mod.__package__ = "etl"
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    mod_norm = sys.modules["etl.normalize_transactions"]
    mod_imp = sys.modules["etl.import_transactions"]
    out["detect_columns"] = getattr(mod_norm, "detect_columns", None)
    out["extract_transaction_section"] = getattr(mod_norm, "extract_transaction_section", None)
    out["normalize_to_canonical"] = getattr(mod_norm, "normalize_to_canonical", None)
    out["import_from_raw_dataframe"] = getattr(mod_imp, "import_from_raw_dataframe", None)
    out["ensure_schema"] = getattr(mod_imp, "ensure_schema", None)
    out["ensure_account"] = getattr(mod_imp, "ensure_account", None)
    return out

try:
    _etl = _load_etl()
except Exception:
    _etl = {}
detect_columns = _etl.get("detect_columns")
extract_transaction_section = _etl.get("extract_transaction_section")
normalize_to_canonical = _etl.get("normalize_to_canonical")
import_from_raw_dataframe = _etl.get("import_from_raw_dataframe")
ensure_schema = _etl.get("ensure_schema")
ensure_account = _etl.get("ensure_account")

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
    conn = sqlite3.connect(DB_PATH)
    if ensure_schema is not None:
        ensure_schema(conn)
    else:
        # Fallback if ETL didn't load: run schema.sql ourselves
        schema_path = os.path.join(PROJECT_ROOT, "models", "schema.sql")
        if os.path.isfile(schema_path):
            with open(schema_path, "r", encoding="utf-8") as f:
                conn.executescript(f.read())
            conn.commit()
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


def category_spend(conn, month: Optional[str] = None) -> pd.DataFrame:
    """Total spending by category (amount < 0, exclude transfer). Optionally filter by month (YYYY-MM)."""
    q = """
        SELECT category, SUM(amount) AS total
        FROM transactions
        WHERE amount < 0 AND (txn_type IS NULL OR txn_type != 'transfer')
    """
    if month:
        q += " AND strftime('%Y-%m', date_posted) = ?"
    q += " GROUP BY category"
    params = (month,) if month else ()
    df = pd.read_sql(q, conn, params=params) if params else pd.read_sql(q, conn)
    return df


def get_available_months(conn) -> list:
    """Distinct months from transactions (YYYY-MM), sorted newest first."""
    df = pd.read_sql(
        "SELECT DISTINCT strftime('%Y-%m', date_posted) AS month FROM transactions WHERE date_posted IS NOT NULL ORDER BY month DESC",
        conn,
    )
    return df["month"].tolist() if not df.empty else []


def load_imports(conn) -> pd.DataFrame:
    """List all imports (file_name, account_id, import_date, row_count)."""
    return pd.read_sql(
        "SELECT import_id, file_name, account_id, import_date, row_count FROM imports ORDER BY import_date DESC",
        conn,
    )


def delete_import(conn, import_id: int) -> int:
    """Delete an import and all its transactions. Returns number of transactions deleted."""
    cur = conn.execute("SELECT COUNT(*) FROM transactions WHERE import_id = ?", (import_id,))
    n = cur.fetchone()[0]
    conn.execute("DELETE FROM transactions WHERE import_id = ?", (import_id,))
    conn.execute("DELETE FROM imports WHERE import_id = ?", (import_id,))
    conn.commit()
    return n


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


def total_spending(conn) -> float:
    """All-time spending (outflows, excluding transfers). Sum of amount where amount < 0, txn_type != transfer."""
    row = conn.execute("""
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM transactions
        WHERE amount < 0 AND (txn_type IS NULL OR txn_type != 'transfer')
    """).fetchone()
    return abs(float(row[0])) if row else 0.0


def total_income(conn) -> float:
    """All-time income (inflows, excluding refunds/transfers)."""
    row = conn.execute("""
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM transactions
        WHERE amount > 0 AND (txn_type IS NULL OR txn_type NOT IN ('refund', 'transfer'))
    """).fetchone()
    return float(row[0]) if row else 0.0


def latest_net_worth(conn) -> float:
    """Net worth from most recent month in snapshots (assets - liabilities)."""
    nw = net_worth_by_month(conn)
    if nw.empty:
        return 0.0
    return float(nw.iloc[-1]["net_worth"])


def this_month_spending(conn) -> float:
    """Spending in the current calendar month."""
    exp = monthly_expenses(conn)
    if exp.empty:
        return 0.0
    this_month = datetime.now().strftime("%Y-%m")
    row = exp[exp["month"] == this_month]
    return abs(float(row["expenses"].sum())) if not row.empty else 0.0


def this_month_income(conn) -> float:
    """Income in the current calendar month."""
    inc = monthly_income(conn)
    if inc.empty:
        return 0.0
    this_month = datetime.now().strftime("%Y-%m")
    row = inc[inc["month"] == this_month]
    return float(row["income"].sum()) if not row.empty else 0.0


# --------------- UI ---------------

st.set_page_config(page_title="Netflow", layout="wide")
st.title("Netflow")

# --------------- Quick summary for new users ---------------
with st.expander("What is this? — Get started", expanded=True):
    st.markdown("""
    **Netflow** is a personal finance tracker that runs in your browser. Your data stays on this device (or server); nothing is sent to a third party.

    **What you can do:**
    - **Track spending & income** — Upload bank or card CSVs; we auto-detect columns (BofA, Amex, and most exports).
    - **See totals** — Total spending, income, net worth, and this month’s numbers at a glance.
    - **View by month** — Use the *View by month* dropdown to filter charts to a single month.
    - **Add investment balances** — For brokerage, crypto (e.g. Coinbase), or other accounts that don’t export CSV, use *Manual balance entry*: enter month, ending balance, deposits, and withdrawals.

    **Quick start:** Go to **Add Data** → **Upload CSV**, pick your bank’s export file, give the account a name, and click *Import transactions*. The summary and charts below will update. Use **Manage imports** to remove a file’s data if you need to.
    """)
    st.caption("Duplicate uploads of the same file are skipped. Transactions are categorized by rules you can edit in the app’s rules folder.")

conn = get_conn()

# --------------- Input methods ---------------
st.header("Add Data")

input_method = st.radio(
    "Input method",
    ["Upload CSV (auto-detect)", "Paste table (tab-separated)", "Manual balance entry"],
    horizontal=True,
)

if input_method == "Upload CSV (auto-detect)":
    if detect_columns is None or extract_transaction_section is None or import_from_raw_dataframe is None:
        st.warning("CSV import module could not be loaded. Upload is unavailable on this deployment.")
    uploaded = st.file_uploader(
        "Upload your bank or card CSV — we'll detect columns automatically",
        type=["csv"],
        help="Supports BofA, Amex, and most CSVs with date, description, and amount (or debit/credit).",
    )
    if uploaded and detect_columns and extract_transaction_section and import_from_raw_dataframe:
        # Try to extract transaction table from multi-section bank CSVs (summary block + Date,Description,Amount)
        df = extract_transaction_section(uploaded, encoding="utf-8")
        if df.empty:
            try:
                uploaded.seek(0)
                df = pd.read_csv(uploaded, on_bad_lines="skip", encoding="utf-8")
            except Exception:
                uploaded.seek(0)
                df = pd.read_csv(uploaded, on_bad_lines="skip", encoding="latin-1")
        else:
            uploaded.seek(0)  # reset for later re-read if needed

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
        if import_from_raw_dataframe is None:
            st.error("Import module could not be loaded. Paste import is unavailable.")
        else:
            try:
                df = pd.read_csv(StringIO(paste), sep="\t", header=None, names=["date", "description", "amount"])
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
        if ensure_schema is not None:
            ensure_schema(conn)
        if ensure_account is not None:
            ensure_account(conn, account_id_manual, account_type=account_type_manual)
        conn.execute(
            "REPLACE INTO monthly_snapshots (month, account_id, ending_balance, deposits, withdrawals) VALUES (?, ?, ?, ?, ?)",
            (month_manual, account_id_manual, ending, deposits, withdrawals),
        )
        conn.commit()
        st.success("Saved.")

conn = get_conn()  # refresh after possible writes

# --------------- Month filter & Manage imports ---------------
available_months = get_available_months(conn)
month_options = ["All"] + available_months
selected_month = st.selectbox(
    "View by month",
    month_options,
    index=0,
    help="Filter charts and totals to a single month or show all.",
)
filter_month = None if selected_month == "All" else selected_month

# Manage imports: list and remove files
with st.expander("Manage imports (remove files)"):
    imports_df = load_imports(conn)
    if imports_df.empty:
        st.caption("No imports yet. Upload a CSV to see it here.")
    else:
        st.dataframe(
            imports_df.rename(columns={"import_id": "ID", "file_name": "File", "account_id": "Account", "import_date": "Date", "row_count": "Rows"}),
            use_container_width=True,
            hide_index=True,
        )
        st.caption("To remove an import and all its transactions, enter the ID above and click Delete.")
        del_id = st.number_input("Import ID to remove", min_value=0, value=0, step=1, key="del_import_id")
        if st.button("Delete this import", type="primary") and del_id:
            n = delete_import(conn, int(del_id))
            st.success(f"Removed import and {n} transactions.")
            st.rerun()

# --------------- Key numbers (total spending, income, net worth) ---------------
st.header("Summary")
# When a month is selected, show that month's totals in summary
if filter_month:
    _exp = monthly_expenses(conn)
    _inc = monthly_income(conn)
    _exp = _exp[_exp["month"] == filter_month]
    _inc = _inc[_inc["month"] == filter_month]
    month_spend = abs(_exp["expenses"].sum()) if not _exp.empty else 0.0
    month_inc = _inc["income"].sum() if not _inc.empty else 0.0
    month_surplus = month_inc - month_spend
else:
    month_spend = this_month_spending(conn)
    month_inc = this_month_income(conn)
    month_surplus = month_inc - month_spend

total_spend = total_spending(conn)
total_inc = total_income(conn)
net_w = latest_net_worth(conn)
all_time_surplus = total_inc - total_spend

# If filtering by month, show that month's spending/income in metrics
if filter_month:
    _exp = monthly_expenses(conn)
    _inc = monthly_income(conn)
    _exp = _exp[_exp["month"] == filter_month]
    _inc = _inc[_inc["month"] == filter_month]
    total_spend_display = abs(_exp["expenses"].sum()) if not _exp.empty else 0.0
    total_inc_display = _inc["income"].sum() if not _inc.empty else 0.0
else:
    total_spend_display = total_spend
    total_inc_display = total_inc

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total spending" + (f" ({filter_month})" if filter_month else " (all time)"), f"${total_spend_display:,.2f}")
c2.metric("Total income" + (f" ({filter_month})" if filter_month else " (all time)"), f"${total_inc_display:,.2f}")
c3.metric("Net worth", f"${net_w:,.2f}")
c4.metric("This month spending", f"${month_spend:,.2f}")
c5.metric("This month surplus", f"${month_surplus:,.2f}", delta=f"Income ${month_inc:,.0f}")

# Second row: savings / net cashflow
with st.expander("More numbers"):
    st.metric("All-time net cashflow (income − spending)", f"${all_time_surplus:,.2f}")
    if total_inc > 0:
        savings_pct = (all_time_surplus / total_inc * 100)
        st.caption(f"Savings rate (all time): {savings_pct:.1f}% of income")

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
if filter_month:
    exp_df = exp_df[exp_df["month"] == filter_month]
if not exp_df.empty:
    exp_df = exp_df.copy()
    exp_df["expenses"] = exp_df["expenses"].abs()
    fig = px.bar(exp_df, x="month", y="expenses", title="Monthly Expenses" + (f" — {filter_month}" if filter_month else ""))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Import transactions to see monthly spending." + (" No data for this month." if filter_month else ""))

# --------------- Spending Categories ---------------
st.header("Spending by Category")
cat_df = category_spend(conn, month=filter_month)
if not cat_df.empty:
    cat_df["total"] = cat_df["total"].abs()
    total_spend = cat_df["total"].sum()
    cat_df["pct"] = (cat_df["total"] / total_spend * 100).round(1)
    fig = px.pie(cat_df, values="total", names="category", title="Spending by Category (%)" + (f" — {filter_month}" if filter_month else ""))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Import transactions to see category breakdown.")

# --------------- Income vs Expenses ---------------
st.header("Income vs Expenses")
inc_df = monthly_income(conn)
exp_df_full = monthly_expenses(conn)
if filter_month:
    exp_df_full = exp_df_full[exp_df_full["month"] == filter_month]
    inc_df = inc_df[inc_df["month"] == filter_month]
if not exp_df_full.empty or not inc_df.empty:
    m = exp_df_full.merge(inc_df, on="month", how="outer").fillna(0)
    m["expenses"] = m["expenses"].abs()
    fig = go.Figure(data=[
        go.Bar(name="Income", x=m["month"], y=m["income"]),
        go.Bar(name="Expenses", x=m["month"], y=m["expenses"]),
    ])
    fig.update_layout(barmode="group", title="Income vs Expenses" + (f" — {filter_month}" if filter_month else ""), xaxis_title="Month")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Import transactions to see income vs expenses." + (" No data for this month." if filter_month else ""))

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
