import streamlit as st, pandas as pd, csv, io
import sys
import os
from pathlib import Path

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
    from lib.supa import client
except ImportError:
    # If direct import fails, fix the path and try again
    try:
        lib_dir = fix_imports()
        from lib.auth import require_auth, get_user_role, get_user_store_id
        from lib.supa import client
    except Exception as e:
        st.error(f"Failed to import required modules: {e}")
        st.error("Please check that all required files are present in the lib directory.")
        st.stop()

st.set_page_config(page_title="Catalog", layout="wide")

token, user = require_auth()
role = get_user_role()

st.title("Catalog")

# Check if we're in development mode
try:
    from lib.db import DEV_MODE, MOCK_PRODUCTS
except ImportError:
    DEV_MODE = False
    MOCK_PRODUCTS = []

if DEV_MODE:
    # Show mock products in development mode
    st.info("🔧 Development Mode - Using Mock Product Catalog")
    df = pd.DataFrame(MOCK_PRODUCTS)
    st.dataframe(df, use_container_width=True)
    
    # Mock categories and product types for development
    categories = ["Beef", "Pork", "Poultry", "Seafood", "Lamb/Goat", "Veal", "Deli/Smoked", "Value-Added"]
    product_types = ["Raw", "Ground", "Marinated", "Value-Added", "Ready-to-Cook", "Ready-to-Eat"]
else:
    # Production mode - use actual Supabase
    supa = client(access_token=token)
    res = supa.table("products").select("*").order("category").order("cut_name").execute()
    df = pd.DataFrame(res.data or [])
    st.dataframe(df, use_container_width=True)
    
    # Get categories and product types from database
    cats_res = supa.table("app_enums").select("value").eq("namespace", "category").execute()
    categories = [r["value"] for r in (cats_res.data or [])]
    
    ptypes_res = supa.table("app_enums").select("value").eq("namespace", "product_type").execute()
    product_types = [r["value"] for r in (ptypes_res.data or [])]

# Only manager/admin can modify catalog
if role not in ("manager","admin"):
    st.info("Product management requires Manager or Admin role.")
    st.stop()

st.subheader("Add Product")
with st.form("add_product"):
    category = st.selectbox("Category", categories)
    cut = st.text_input("Cut name", max_chars=100)
    ptype = st.selectbox("Product type", product_types)
    upc = st.text_input("UPC/SKU (optional)", max_chars=50)
    grade = st.text_input("Grade/Spec (optional)", max_chars=100)
    
    submitted = st.form_submit_button("Add Product")
    if submitted and category and cut and ptype:
        if DEV_MODE:
            # Mock product addition for development
            new_product = {
                "id": len(MOCK_PRODUCTS) + 1,
                "category": category,
                "cut_name": cut,
                "product_type": ptype,
                "upc_sku": upc or "",
                "grade_spec": grade or "",
                "is_active": True
            }
            MOCK_PRODUCTS.append(new_product)
            st.success(f"✅ Mock product added: {category} • {cut} • {ptype}")
            st.rerun()
        else:
            # Production mode - actual database insert
            try:
                result = supa.table("products").insert({
                    "category": category, 
                    "cut_name": cut, 
                    "product_type": ptype,
                    "upc_sku": upc or None, 
                    "grade_spec": grade or None
                }).execute()
                if result.data:
                    st.success("Product added successfully.")
                    st.rerun()
                else:
                    st.error("Failed to add product.")
            except Exception as e:
                if "unique" in str(e).lower():
                    st.error("Product with this category/cut/type combination already exists.")
                else:
                    st.error(f"Error adding product: {e}")

st.subheader("Bulk Import (CSV)")
if DEV_MODE:
    st.info("📁 Development Mode: Upload CSV with columns: category, cut_name, product_type, grade_spec")
else:
    st.info("Upload CSV with columns: category, cut_name, product_type, grade_spec")

file = st.file_uploader("Upload products_seed.csv", type=["csv"])
if file:
    try:
        df_upload = pd.read_csv(file)
        required_cols = ["category", "cut_name", "product_type"]
        if not all(col in df_upload.columns for col in required_cols):
            st.error(f"CSV must contain columns: {', '.join(required_cols)}")
        else:
            rows = df_upload.to_dict(orient="records")
            success_count = 0
            error_count = 0
            
            if DEV_MODE:
                # Mock bulk import for development
                for r in rows:
                    try:
                        new_product = {
                            "id": len(MOCK_PRODUCTS) + success_count + 1,
                            "category": r["category"],
                            "cut_name": r["cut_name"],
                            "product_type": r["product_type"],
                            "grade_spec": r.get("grade_spec", ""),
                            "upc_sku": "",
                            "is_active": True
                        }
                        MOCK_PRODUCTS.append(new_product)
                        success_count += 1
                    except Exception as e:
                        error_count += 1
            else:
                # Production mode - actual database upsert
                for r in rows:
                    try:
                        supa.table("products").upsert({
                            "category": r["category"],
                            "cut_name": r["cut_name"],
                            "product_type": r["product_type"],
                            "grade_spec": r.get("grade_spec")
                        }, on_conflict="category,cut_name,product_type").execute()
                        success_count += 1
                    except Exception as e:
                        error_count += 1
                        
            st.success(f"Import completed: {success_count} successful, {error_count} errors.")
            if success_count > 0:
                st.rerun()
    except Exception as e:
        st.error(f"Error processing file: {e}")
