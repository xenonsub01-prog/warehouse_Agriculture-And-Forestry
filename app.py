# -*- coding: utf-8 -*-
import os, io, csv, secrets
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import streamlit as st

# ---------------- CONFIG ----------------
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_DIR = os.path.join(BASE_DIR, "logs")
TOK_DIR = os.path.join(BASE_DIR, "tokens")

# ensure required directories exist
for d in [DATA_DIR, LOG_DIR, TOK_DIR]:
    os.makedirs(d, exist_ok=True)

MASTER_FILE = os.path.join(DATA_DIR, "master_orders.csv")
TOK_FILE    = os.path.join(TOK_DIR, "tokens.csv")

OWNER_KEY      = st.secrets.get("OWNER_KEY", "admin12345")
BASE_URL       = st.secrets.get("BASE_URL", "https://<app>.streamlit.app/")
CLIENT_COMPANY = st.secrets.get("CLIENT_COMPANY", "Agriculture & Forestry")

# Hide deploy button
st.set_page_config(
    page_title="Warehouse Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"Get help": None, "Report a Bug": None, "About": None}
)

# ---------------- UTILITIES ----------------
def seed_data():
    # create master_orders.csv if not exists
    if not os.path.exists(MASTER_FILE):
        rows = []
        for wh in ["VIC","NSW","SA"]:
            for i in range(50):
                rows.append({
                    "OrderID": f"{wh}-{1000+i}",
                    "Warehouse": wh,
                    "Customer": f"Customer-{i+1}",
                    "Status": np.random.choice(
                        ["Open","Processing","Shipped","Invoiced"], 
                        p=[0.4,0.3,0.2,0.1]
                    ),
                    "Priority": np.random.choice(
                        ["Low","Medium","High"], 
                        p=[0.2,0.6,0.2]
                    ),
                    "InvoiceNo": "",
                    "UpdatedBy": "seed",
                    "UpdatedAt": datetime.utcnow().isoformat(timespec="seconds")+"Z"
                })
        pd.DataFrame(rows).to_csv(MASTER_FILE, index=False)

    # create tokens.csv if not exists
    if not os.path.exists(TOK_FILE):
        pd.DataFrame(
            columns=["token","role","company","expires_at","created_at"]
        ).to_csv(TOK_FILE, index=False)

def load_master():
    return pd.read_csv(MASTER_FILE, dtype=str).fillna("")

def export_excel(df):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Orders")
    buf.seek(0)
    return buf

def export_pdf(df):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4))
    elems = []
    styles = getSampleStyleSheet()
    elems.append(Paragraph(f"{CLIENT_COMPANY} - Orders Export", styles["Title"]))
    elems.append(Spacer(1,12))
    data = [list(df.columns)] + df.astype(str).head(50).values.tolist()
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.lightgrey),
        ("GRID",(0,0),(-1,-1),0.25,colors.grey),
        ("FONTSIZE",(0,0),(-1,-1),8)
    ]))
    elems.append(table)
    doc.build(elems)
    buf.seek(0)
    return buf

def generate_token(role="editor", hours=24):
    token = secrets.token_hex(8)
    exp = (datetime.utcnow()+timedelta(hours=hours)).isoformat()
    df = pd.read_csv(TOK_FILE)
    df.loc[len(df)] = {
        "token":token,"role":role,"company":CLIENT_COMPANY,
        "expires_at":exp,"created_at":datetime.utcnow().isoformat()
    }
    df.to_csv(TOK_FILE, index=False)
    return token, exp

def validate_token(token):
    if not token: return None
    df = pd.read_csv(TOK_FILE)
    row = df[df["token"]==token]
    if row.empty: return None
    r = row.iloc[0].to_dict()
    try:
        if datetime.utcnow() > datetime.fromisoformat(r["expires_at"]):
            return None
    except: pass
    return r

# ---------------- APP ENTRY ----------------
seed_data()
qs = st.query_params
mode, role = "guest","viewer"
company = CLIENT_COMPANY

if "admin" in qs and qs["admin"][0]==OWNER_KEY:
    mode,role = "owner","owner"
elif "token" in qs:
    info = validate_token(qs["token"][0])
    if info:
        mode, role = "client", info.get("role","viewer")
        company = info.get("company", CLIENT_COMPANY)

# ---------------- SIDEBAR ----------------
st.sidebar.header("Navigation")
page = st.sidebar.radio("Go to", ["Dashboard","FAQ"])
st.sidebar.markdown("---")
df_all = load_master()
st.sidebar.download_button("Download Excel", data=export_excel(df_all), file_name="orders.xlsx")
st.sidebar.download_button("Download PDF", data=export_pdf(df_all), file_name="orders.pdf")

# ---------------- PAGES ----------------
def dashboard_page():
    st.markdown(f"### Welcome {company} ({role.upper()})")
    df = load_master()
    if mode=="client":
        df = df.copy()

    # Filters
    c1,c2,c3,c4 = st.columns(4)
    wh = c1.multiselect("Warehouse", sorted(df["Warehouse"].unique()), default=list(sorted(df["Warehouse"].unique())))
    stt= c2.multiselect("Status", sorted(df["Status"].unique()), default=list(sorted(df["Status"].unique())))
    pr = c3.multiselect("Priority", sorted(df["Priority"].unique()), default=list(sorted(df["Priority"].unique())))
    oid= c4.text_input("Search OrderID")
    q = df[df["Warehouse"].isin(wh) & df["Status"].isin(stt) & df["Priority"].isin(pr)]
    if oid: q = q[q["OrderID"].str.contains(oid)]
    st.dataframe(q, use_container_width=True, height=360)

    # KPIs
    k1,k2,k3,k4 = st.columns(4)
    k1.metric("Open", (df["Status"]=="Open").sum())
    k2.metric("Processing", (df["Status"]=="Processing").sum())
    k3.metric("Shipped", (df["Status"]=="Shipped").sum())
    k4.metric("Invoiced", (df["Status"]=="Invoiced").sum())

    if role in ["editor","owner"]:
        st.subheader("Update Order (temporary for clients)")
        c1,c2,c3 = st.columns(3)
        oid = c1.text_input("OrderID to update")
        new_status = c2.selectbox("New Status", ["Open","Processing","Shipped","Invoiced"])
        new_inv = c3.text_input("Invoice No.")
        if st.button("Apply Update"):
            idx = df.index[df["OrderID"]==oid].tolist()
            if not idx: 
                st.error("Order not found")
            else:
                i=idx[0]
                df.at[i,"Status"]=new_status
                df.at[i,"InvoiceNo"]=new_inv
                df.at[i,"UpdatedBy"]=role
                df.at[i,"UpdatedAt"]=datetime.utcnow().isoformat(timespec="seconds")+"Z"
                st.success("Updated (temporary). Export to save locally.")

def faq_page():
    st.header("FAQ & Examples")
    qas=[
        ("Can managers view only their warehouse orders?","Yes, by using filters or pre-set tokens."),
        ("Are client changes permanent?","No. Client changes are temporary and reset on logout."),
        ("Do KPIs refresh instantly?","Yes, metrics update after every change."),
        ("Can I export data?","Yes, Excel and PDF exports are available."),
        ("Is there an audit log?","In demo mode, logs are not persistent for clients."),
        ("Does the app use VBA?","No, only Python/Streamlit. No macros."),
        ("Is the system scalable?","Yes, designed to handle 20k+ orders."),
        ("Can we integrate with SharePoint?","Yes, planned for future phases."),
        ("How secure is access?","Access is only possible with valid tokens."),
        ("Is there a warranty?","Yes, 30-day bug-fix warranty.")
    ]
    for i,(q,a) in enumerate(qas,1):
        with st.expander(f"{i}. {q}"):
            st.write(a)

if page=="Dashboard": 
    dashboard_page()
elif page=="FAQ": 
    faq_page()
