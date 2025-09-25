import streamlit as st, pandas as pd
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta

# Fix imports for Streamlit Cloud deployment
def fix_imports():
    """Fix import paths for different deployment environments"""
    current_file = Path(__file__).resolve()
    
    # Get the directory containing this file (should be /app/pages)
    pages_dir = current_file.parent
    app_dir = pages_dir.parent
    lib_dir = app_dir / "lib"
    
    # Check if lib directory exists in the expected location
    if lib_dir.exists() and (lib_dir / "auth.py").exists():
        # Add app directory to Python path if not already there
        if str(app_dir) not in sys.path:
            sys.path.insert(0, str(app_dir))
        return lib_dir
    
    # Fallback: try to find lib directory by walking up the directory tree
    for parent in current_file.parents:
        potential_lib = parent / "lib"
        if potential_lib.exists() and (potential_lib / "auth.py").exists():
            if str(parent) not in sys.path:
                sys.path.insert(0, str(parent))
            return potential_lib
    
    raise ImportError(f"Could not find lib directory with auth.py. Current file: {current_file}")

try:
    # Try direct import first
    from lib.auth import require_auth, get_user_role, get_user_store_id
    from lib.db import filter_events
    from lib.charts import bar_cost_by_category, pareto_top_products, line_daily_trend, donut_event_mix
    from lib.supa import client
except ImportError:
    # If direct import fails, fix the path and try again
    try:
        lib_dir = fix_imports()
        from lib.auth import require_auth, get_user_role, get_user_store_id
        from lib.db import filter_events
        from lib.charts import bar_cost_by_category, pareto_top_products, line_daily_trend, donut_event_mix
        from lib.supa import client
    except Exception as e:
        st.error(f"Failed to import required modules: {e}")
        st.error("Please check that all required files are present in the lib directory.")
        st.stop()

st.set_page_config(page_title="Reports", layout="wide")

token, user = require_auth()
store_id = get_user_store_id()
role = get_user_role()

st.title("Reports")

with st.sidebar:
    st.subheader("Filters")
    preset = st.selectbox("Date preset", ["Today","Last 7 days","Month to date","Custom"])
    today = datetime.utcnow().date()
    if preset == "Today":
        date_from = datetime.combine(today, datetime.min.time())
        date_to = datetime.combine(today, datetime.max.time())
    elif preset == "Last 7 days":
        date_from = datetime.utcnow() - timedelta(days=7)
        date_to = datetime.utcnow()
    elif preset == "Month to date":
        date_from = datetime(datetime.utcnow().year, datetime.utcnow().month, 1)
        date_to = datetime.utcnow()
    else:
        date_from = st.date_input("From", value=today - timedelta(days=7), key="f_date_from")
        date_to = st.date_input("To", value=today, key="f_date_to")

    # Simplified filter options for development
    categories = ["Beef", "Pork", "Poultry", "Seafood", "Lamb/Goat", "Veal", "Deli/Smoked", "Value-Added"]
    product_types = ["Raw", "Ground", "Marinated", "Value-Added", "Ready-to-Cook", "Ready-to-Eat"]
    event_types = ["Spoilage", "Trim/Waste", "Theft", "Damage", "Markdown", "Rework", "Return"]
    cuts = ["Ribeye", "Ground Beef 80/20", "Pork Loin Center Cut", "Boneless Skinless Breast", "Salmon Fillet Atlantic"]

    cats = st.multiselect("Category", categories, key="f_category")
    cuts_filtered = st.multiselect("Cut", cuts, key="f_cut")
    ptypes = st.multiselect("Product Type", product_types, key="f_product_type")
    etypes = st.multiselect("Event Type", event_types, key="f_event_type")
    
    # Store filter for auditor/admin
    selected_store = None
    if role in ("auditor", "admin"):
        selected_store = st.number_input("Store ID (optional)", min_value=1, value=None, key="f_store_id")

    # Measure toggle
    measure = st.selectbox("Measure", ["Cost", "Weight", "Retail Value"], key="f_measure")

filters = {
    "store_id": selected_store if role in ("auditor","admin") else store_id,
    "date_from": date_from.isoformat() if isinstance(date_from, datetime) else str(date_from),
    "date_to": (datetime.combine(date_to, datetime.max.time()) if not isinstance(date_to, datetime) else date_to).isoformat(),
    "category": cats or None,
    "cut_name": cuts_filtered or None,
    "product_type": ptypes or None,
    "event_type": etypes or None,
}

rows = filter_events(token, filters)
df = pd.DataFrame(rows)

if df.empty:
    st.info("No data for current selection. Try recording some shrink events first!")
    
    # Show sample data message in development
    from lib.db import DEV_MODE
    if DEV_MODE:
        st.info("💡 **Development Mode**: Go to the 'Record Shrink' page to create some sample data first, then come back here to see charts and reports.")
    st.stop()

df["shrink_cost"] = df["weight_lbs"] * df["unit_cost"]
df["retail_value"] = df["weight_lbs"] * df["unit_price"]

# Map measure selection to column
measure_col = {
    "Cost": "shrink_cost",
    "Weight": "weight_lbs", 
    "Retail Value": "retail_value"
}[measure]

colA, colB = st.columns(2)
with colA:
    st.plotly_chart(bar_cost_by_category(df, measure_col), use_container_width=True)
with colB:
    st.plotly_chart(donut_event_mix(df, measure_col), use_container_width=True)

st.plotly_chart(line_daily_trend(df, measure_col), use_container_width=True)
st.plotly_chart(pareto_top_products(df, 20, measure_col), use_container_width=True)

st.subheader("Filtered Data")
# Limit display to 10k rows as per design
display_df = df.head(10000) if len(df) > 10000 else df
if len(df) > 10000:
    st.warning(f"Showing first 10,000 of {len(df)} rows. Use exports for full dataset.")

st.dataframe(display_df, use_container_width=True, height=400)
