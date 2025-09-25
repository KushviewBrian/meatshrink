import streamlit as st
import pandas as pd
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta

# Fix imports for Streamlit Cloud deployment
try:
    # Try direct import first
    from lib.auth import require_auth, get_user_role, get_user_store_id
    from lib.supa import client
except ImportError:
    # If direct import fails, fix the path and try again
    current_file = Path(__file__).resolve()
    pages_dir = current_file.parent
    app_dir = pages_dir.parent
    
    # Add app directory to Python path
    if str(app_dir) not in sys.path:
        sys.path.insert(0, str(app_dir))
    
    # Now try importing again
    from lib.auth import require_auth, get_user_role, get_user_store_id
    from lib.supa import client

st.set_page_config(page_title="Admin & Audit", layout="wide")

token, user = require_auth()
role = get_user_role()

st.title("Admin & Audit")

# Only admin can access this page
if role != "admin":
    st.error("Admin access required.")
    st.stop()

supa = client(access_token=token)

st.subheader("Users Management")
try:
    users_res = supa.table("app_users").select("*").order("email").execute()
    users_df = pd.DataFrame(users_res.data or [])
    if not users_df.empty:
        st.dataframe(users_df, use_container_width=True)
    else:
        st.info("No users found in app_users table.")
except Exception as e:
    st.error(f"Error loading users: {e}")

st.subheader("Audit Log (latest 200)")
try:
    audit_res = supa.table("audit_log").select("*").order("at", desc=True).limit(200).execute()
    audit_df = pd.DataFrame(audit_res.data or [])
    if not audit_df.empty:
        st.dataframe(audit_df, use_container_width=True)
    else:
        st.info("No audit records found.")
except Exception as e:
    st.error(f"Error loading audit log: {e}")

st.subheader("System Maintenance")
col1, col2 = st.columns(2)

with col1:
    if st.button("Refresh Materialized Views", type="primary"):
        try:
            # Use service role client for admin operations
            admin_supa = client(anon=False)  # This uses SUPABASE_SERVICE_ROLE
            
            # Execute raw SQL to refresh materialized views
            admin_supa.postgrest.rpc('refresh_materialized_views').execute()
            st.success("Materialized views refreshed successfully.")
        except Exception as e:
            # Fallback to direct SQL execution
            try:
                # Alternative approach using raw SQL
                refresh_sql = """
                REFRESH MATERIALIZED VIEW CONCURRENTLY mv_shrink_daily_store;
                REFRESH MATERIALIZED VIEW CONCURRENTLY mv_shrink_daily_store_category;
                """
                # Note: This requires a custom RPC function in Supabase or direct DB access
                st.warning(f"MV refresh failed with RPC, manual refresh needed: {e}")
                st.code(refresh_sql, language="sql")
            except Exception as e2:
                st.error(f"Failed to refresh materialized views: {e2}")

with col2:
    if st.button("System Health Check"):
        st.info("Checking system health...")
        
        # Check table counts
        try:
            events_count = len(supa.table("shrink_events").select("id", count="exact").execute().data or [])
            products_count = len(supa.table("products").select("id", count="exact").execute().data or [])
            users_count = len(supa.table("app_users").select("id", count="exact").execute().data or [])
            
            st.success(f"""
            **System Status**: ✅ Healthy
            - Shrink Events: {events_count:,}
            - Products: {products_count:,}
            - Users: {users_count:,}
            """)
        except Exception as e:
            st.error(f"Health check failed: {e}")

st.subheader("Database Maintenance")
st.info("""
**Regular Maintenance Tasks:**
- Materialized views should be refreshed nightly at 02:30 UTC
- Backup verification should be performed monthly
- Audit log cleanup (retain 1 year of records)
- Export files cleanup (retain 90 days)

**Manual Operations:**
Use the refresh button above to update materialized views on-demand.
""")

# Display some key metrics
st.subheader("Key Metrics")
try:
    today_events = supa.table("shrink_events").select("id", count="exact").gte("created_at", pd.Timestamp.now().date().isoformat()).execute()
    st.metric("Today's Events", len(today_events.data or []))
except Exception as e:
    st.error(f"Error loading metrics: {e}")
