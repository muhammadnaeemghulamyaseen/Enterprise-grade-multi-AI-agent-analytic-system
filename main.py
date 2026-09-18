import streamlit as st
import pandas as pd
import plotly.express as px
from pyairtable import Api
from datetime import datetime

# ------------------------------------------------------------------
# PAGE CONFIG
# ------------------------------------------------------------------
st.set_page_config(
    page_title="E-Commerce Live Dashboard",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🛍️ Sales & Orders Live Dashboard")
st.caption("Real-time E-commerce insights • Automated cleaning • Dynamic Charts")

# ------------------------------------------------------------------
# SIDEBAR — Airtable credentials
# ------------------------------------------------------------------
st.sidebar.header("🔐 Airtable Connection")

try:
    default_token = st.secrets.get("AIRTABLE_TOKEN", "")
    default_base  = st.secrets.get("AIRTABLE_BASE_ID", "")
    default_table = st.secrets.get("AIRTABLE_TABLE_NAME", "")
except Exception:
    default_token = ""
    default_base  = ""
    default_table = ""

api_token  = st.sidebar.text_input("Personal Access Token", value=default_token, type="password")
base_id    = st.sidebar.text_input("Base ID", value=default_base, placeholder="appXXXXXXXXXXXXXX")
table_name = st.sidebar.text_input("Table Name", value=default_table, placeholder="My Table")

fetch_btn = st.sidebar.button("🔄 Fetch / Refresh Data", use_container_width=True)

# ------------------------------------------------------------------
# DATA FETCHING
# ------------------------------------------------------------------
@st.cache_data(ttl=30, show_spinner=False)
def fetch_airtable_data(token: str, base_id: str, table_name: str) -> pd.DataFrame:
    api = Api(token)
    table = api.table(base_id, table_name)
    records = table.all()

    rows = []
    for rec in records:
        row = rec.get("fields", {}).copy()
        row["_record_id"] = rec.get("id")
        rows.append(row)

    df = pd.DataFrame(rows)
    return df

# ------------------------------------------------------------------
# SESSION STATE INITIALIZATION
# ------------------------------------------------------------------
if "df" not in st.session_state:
    st.session_state.df = None
if "df_original" not in st.session_state:
    st.session_state.df_original = None
if "last_fetch" not in st.session_state:
    st.session_state.last_fetch = None

def load_data():
    try:
        with st.spinner("Fetching live orders from Airtable..."):
            df = fetch_airtable_data(api_token, base_id, table_name)
        
        # Ensure standard data types for business mapping
        for col in df.columns:
            if 'price' in col.lower() or 'quantity' in col.lower():
                df[col] = pd.to_numeric(df[col], errors='coerce')
                
        st.session_state.df = df.copy()
        st.session_state.df_original = df.copy()
        st.session_state.last_fetch = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.success(f"✅ Loaded {len(df)} orders successfully!")
    except Exception as e:
        st.error(f"❌ Connection Failed: {e}")

if fetch_btn:
    if not (api_token and base_id and table_name):
        st.sidebar.warning("Please fill in all connection fields.")
    else:
        load_data()
        st.cache_data.clear()

# Stop execution if data is not loaded yet
if st.session_state.df is None:
    st.info("👈 Please enter your Airtable credentials in the sidebar and click **Fetch / Refresh Data**.")
    st.stop()

df: pd.DataFrame = st.session_state.df

if st.session_state.last_fetch:
    st.markdown(f"**Last Sync Time:** `{st.session_state.last_fetch}`")

# ------------------------------------------------------------------
# DYNAMIC COLUMN MAPPING (CRITICAL FIX FOR GRAPH GARBAR)
# ------------------------------------------------------------------
# Auto-detect fields based on user dataset pattern
col_list = df.columns.tolist()
prod_col = next((c for c in col_list if 'product' in c.lower() or 'name' in c.lower()), col_list[1] if len(col_list)>1 else col_list[0])
cat_col = next((c for c in col_list if 'cat' in c.lower() or 'type' in c.lower()), col_list[2] if len(col_list)>2 else col_list[0])
price_col = next((c for c in col_list if 'price' in c.lower() or 'rate' in c.lower()), col_list[3] if len(col_list)>3 else col_list[0])
qty_col = next((c for c in col_list if 'qty' in c.lower() or 'quant' in c.lower()), col_list[4] if len(col_list)>4 else col_list[0])
status_col = next((c for c in col_list if 'status' in c.lower() or 'stage' in c.lower()), col_list[6] if len(col_list)>6 else col_list[0])

# Ensure numeric format for metrics calculation
df[price_col] = pd.to_numeric(df[price_col], errors='coerce').fillna(0.0)
df[qty_col] = pd.to_numeric(df[qty_col], errors='coerce').fillna(0.0)
df['Total_Sales'] = df[price_col] * df[qty_col]

# ------------------------------------------------------------------
# LIVE DATA HEALTH METRICS
# ------------------------------------------------------------------
total_rows = len(df)
missing_vals = int(df.isna().sum().sum())
duplicate_rows = int(df.duplicated(subset=[c for c in df.columns if not c.startswith('_')]).sum())
total_revenue = float(df['Total_Sales'].sum())

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Orders (Rows)", f"{total_rows:,}")
m2.metric("Total Revenue generated", f"${total_revenue:,.2f}")
m3.metric("Data Missing Values", f"{missing_vals:,}")
m4.metric("Duplicate Orders", f"{duplicate_rows:,}")

st.divider()

# ------------------------------------------------------------------
# ONE-CLICK CLEANING PIPELINE
# ------------------------------------------------------------------
c1, c2, _ = st.columns([1, 1, 2])
with c1:
    clean_btn = st.button("🧼 Clean & Normalize Data", type="primary", use_container_width=True)
with c2:
    reset_btn = st.button("↩️ Reset to Raw Data", use_container_width=True)

if clean_btn:
    cleaned = df.copy()
    
    # 1. Deduplicate based on core business data (ignoring unique database record ids)
    core_cols = [c for c in cleaned.columns if not c.startswith('_') and c != 'Total_Sales']
    cleaned = cleaned.drop_duplicates(subset=core_cols)
    
    # 2. Fix missing status or categories
    if status_col in cleaned.columns:
        cleaned[status_col] = cleaned[status_col].fillna("Pending").astype(str).str.strip()
    if cat_col in cleaned.columns:
        cleaned[cat_col] = cleaned[cat_col].fillna("General").astype(str).str.strip()
    if prod_col in cleaned.columns:
        cleaned[prod_col] = cleaned[prod_col].fillna("Unknown Item").astype(str).str.strip()
        
    # 3. Handle numerical missing values safely using median values
    cleaned[price_col] = cleaned[price_col].replace(0, cleaned[price_col].median() if cleaned[price_col].median() > 0 else 10.0)
    cleaned[qty_col] = cleaned[qty_col].replace(0, 1.0)
    cleaned['Total_Sales'] = cleaned[price_col] * cleaned[qty_col]

    st.session_state.df = cleaned
    st.success("🎉 Data cleaning successfully applied! String spaces stripped, duplicates dropped, null statuses fixed.")
    st.rerun()

if reset_btn and st.session_state.df_original is not None:
    st.session_state.df = st.session_state.df_original.copy()
    st.success("↩️ Reset successfully performed.")
    st.rerun()

# ------------------------------------------------------------------
# HIGH-END BUSINESS VISUALIZATIONS
# ------------------------------------------------------------------
st.subheader("📊 Dynamic Business Insights")

t1, t2, t3 = st.tabs(["💰 Financial Performance", "📦 Category & Product Mix", "⚙️ Fulfillment Status"])

with t1:
    col_t1_a, col_t1_b = st.columns(2)
    with col_t1_a:
        # Revenue by Category
        rev_cat = df.groupby(cat_col)['Total_Sales'].sum().reset_index().sort_values(by='Total_Sales', ascending=False)
        fig_rev = px.bar(rev_cat, x=cat_col, y='Total_Sales', title="Revenue Contribution by Category ($)",
                         color='Total_Sales', color_continuous_scale="Blues", labels={'Total_Sales':'Revenue'})
        st.plotly_chart(fig_rev, use_container_width=True)
    with col_t1_b:
        # Price distribution of items
        fig_box = px.box(df, x=cat_col, y=price_col, title="Product Pricing Distribution across Categories", color=cat_col)
        st.plotly_chart(fig_box, use_container_width=True)

with t2:
    col_t2_a, col_t2_b = st.columns(2)
    with col_t2_a:
        # Volume Share by Category
        cat_share = df[cat_col].value_counts().reset_index()
        cat_share.columns = [cat_col, 'Count']
        fig_pie = px.pie(cat_share, values='Count', names=cat_col, title="Order Volume Breakdown by Category", hole=0.4)
        st.plotly_chart(fig_pie, use_container_width=True)
    with col_t2_b:
        # Top Products
        top_prod = df.groupby(prod_col)[qty_col].sum().reset_index().sort_values(by=qty_col, ascending=False).head(8)
        fig_prod = px.bar(top_prod, x=qty_col, y=prod_col, orientation='h', title="Top 8 Products by Units Sold",
                          color=qty_col, color_continuous_scale="Viridis")
        fig_prod.update_layout(yaxis={'categoryorder':'total ascending'})
        st.plotly_chart(fig_prod, use_container_width=True)

with t3:
    if status_col in df.columns:
        status_count = df[status_col].fillna("Missing/Blank").astype(str).value_counts().reset_index()
        status_count.columns = [status_col, 'Total Orders']
        
        fig_status = px.bar(status_count, x=status_col, y='Total Orders', color=status_col,
                            title="Order Fulfillment Pipeline Tracking",
                            color_discrete_map={"Delivered": "#2ecc71", "Shipped": "#3498db", "Pending": "#f1c40f", "Missing/Blank": "#e74c3c"})
        st.plotly_chart(fig_status, use_container_width=True)
    else:
        st.info("Status data field not available.")

# Preview Raw Data Matrix (Fixed Indentation)
with st.expander("🔍 Explore Current Active Data Matrix Table", expanded=False):
    st.dataframe(df, use_container_width=True)

# ------------------------------------------------------------------
# N8N AUTOMATION MULTI-AI AGENT PIPELINE INTEGRATION
# ------------------------------------------------------------------
st.divider()
st.subheader("🤖 Autonomous n8n Multi-AI Agent Orchestration")
st.caption("Send parsed datasets matrices directly to your n8n workflows cluster containing Agent 1, 2, and 3.")

# Safe initialization for transmission responses states
if "n8n_response_status" not in st.session_state:
    st.session_state.n8n_response_status = None

# Input field to safely hold n8n Webhook URL endpoint configurations
n8n_webhook_default = st.secrets.get("N8N_WEBHOOK_URL", "") if hasattr(st, "secrets") else ""
n8n_url = st.text_input("https://end-to-end-data-pipeline.app.n8n.cloud/webhook-test/streamlit-data-ingestion")

# Execution trigger for n8n cloud data transmission
import requests
send_to_n8n = st.button("🚀 Trigger Multi-AI Agents & Whatsapp Dispatch", type="secondary", use_container_width=True)

if send_to_n8n:
    if not n8n_url:
        st.warning("⚠️ Configuration Alert: Please configure your active n8n production webhook URL network instance.")
    else:
        with st.spinner("📦 Parsing data metrics, building payload matrix, and streaming to n8n AI cluster..."):
            try:
                # 1. Compress core operations column metrics for optimal LLM context window ingestion
                records_payload = df[[prod_col, cat_col, price_col, qty_col, 'Total_Sales', status_col]].to_dict(orient="records")
                
                # 2. Build explicit operational business parameters metadata
                payload_json = {
                    "metadata": {
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "total_orders": int(total_rows),
                        "gross_revenue": float(total_revenue),
                        "missing_data_points": int(missing_vals),
                        "pipeline_redundancies": int(duplicate_rows)
                    },
                    "orders_dataset": records_payload
                }
                
                # 3. Stream transaction execution via HTTP POST API request protocols
                response = requests.post(n8n_url, json=payload_json, headers={"Content-Type": "application/json"}, timeout=30)
                
                if response.status_code == 200:
                    st.session_state.n8n_response_status = f"✅ Success (200): Core parameters dispatched smoothly. n8n multi-agent node network initialized successfully!"
                    st.success(st.session_state.n8n_response_status)
                else:
                    st.session_state.n8n_response_status = f"⚠️ Server Alert ({response.status_code}): Data streamed, but n8n pipeline returned an unexpected status code."
                    st.warning(st.session_state.n8n_response_status)
                    
            except Exception as n8n_err:
                st.error(f"❌ Transmission Error Interrupted: Connection failed to n8n server instance. Details: {str(n8n_err)}")
