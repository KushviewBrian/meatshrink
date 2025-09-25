import streamlit as st
import pandas as pd
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
    from lib.exports import generate_csv_export, generate_xlsx_export, upload_to_storage, get_signed_url
except ImportError:
    # If direct import fails, fix the path and try again
    try:
        lib_dir = fix_imports()
        from lib.auth import require_auth, get_user_role, get_user_store_id
        from lib.db import filter_events
        from lib.exports import generate_csv_export, generate_xlsx_export, upload_to_storage, get_signed_url
    except Exception as e:
        st.error(f"Failed to import required modules: {e}")
        st.error("Please check that all required files are present in the lib directory.")
        st.stop()

st.set_page_config(page_title="Exports", layout="wide")

token, user = require_auth()
store_id = get_user_store_id()
role = get_user_role()

st.title("Exports")

with st.sidebar:
    st.subheader("Filters")
    date_from = st.date_input("From", value=datetime.utcnow().date()-timedelta(days=7))
    date_to = st.date_input("To", value=datetime.utcnow().date())
    report_name = st.text_input("Report name", value="current_selection")
    
    # Store filter for auditor/admin
    selected_store = store_id
    if role in ("auditor", "admin"):
        selected_store = st.number_input("Store ID", min_value=1, value=store_id or 1)

rows = filter_events(token, {
    "store_id": selected_store,
    "date_from": datetime.combine(date_from, datetime.min.time()).isoformat(),
    "date_to": datetime.combine(date_to, datetime.max.time()).isoformat()
})
df = pd.DataFrame(rows)

if df.empty:
    st.info("No data for current selection.")
else:
    st.dataframe(df, use_container_width=True, height=400)

    c1,c2 = st.columns(2)
    with c1:
        if st.button("Export CSV"):
            try:
                url = export_and_upload(token, df, selected_store, report_name, fmt="csv")
                st.success(f"CSV exported successfully!")
                st.info(f"Download URL (expires in 15 min): {url}")
            except Exception as e:
                st.error(f"Export failed: {e}")
    with c2:
        if st.button("Export XLSX"):
            try:
                url = export_and_upload(token, df, selected_store, report_name, fmt="xlsx")
                st.success(f"XLSX exported successfully!")
                st.info(f"Download URL (expires in 15 min): {url}")
            except Exception as e:
                st.error(f"Export failed: {e}")

st.subheader("Export Information")
st.info("""
**Export Format**: Files are named `shrink_{store_id}_{YYYYMMDD}_{report_name}.{csv|xlsx}`

**Columns**: id, store_id, date_time_iso, category, cut_name, product_type, event_type, weight_lbs, unit_cost, unit_price, shrink_cost, retail_value, entered_by_email, notes

**Retention**: Files are kept for 90 days in Supabase Storage.
""")
