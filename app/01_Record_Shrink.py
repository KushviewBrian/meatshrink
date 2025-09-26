import streamlit as st
import pandas as pd
import sys
import os
from pathlib import Path
from datetime import datetime, timezone, time as time_type

# Simplified import fix for Streamlit Cloud deployment
def fix_imports():
    """Fix import paths for different deployment environments"""
    current_file = Path(__file__).resolve()
    
    # Get the directory containing this file (should be /app)
    app_dir = current_file.parent
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
    # Try to import directly first (works in most cases)
    from lib.auth import require_auth, get_user_role, get_user_store_id
    from lib.db import list_products, list_event_types, insert_shrink_event, list_recent_events, create_correction
    from lib.validators import validate_weight, validate_prices, validate_datetime
    # Import OCR functionality
    from lib.ocr import process_uploaded_image, display_extraction_results
except ImportError:
    # If direct import fails, fix the path and try again
    try:
        lib_dir = fix_imports()
        from lib.auth import require_auth, get_user_role, get_user_store_id
        from lib.db import list_products, list_event_types, insert_shrink_event, list_recent_events, create_correction
        from lib.validators import validate_weight, validate_prices, validate_datetime
        from lib.ocr import process_uploaded_image, display_extraction_results
    except Exception as e:
        st.error(f"Failed to import required modules: {e}")
        st.error("Please check that all required files are present in the lib directory.")
        st.stop()

st.set_page_config(page_title="Record Shrink - Seaway Marketplace", layout="wide", initial_sidebar_state="collapsed")

# Custom CSS for Seaway Marketplace branding
st.markdown("""
<style>
    /* Main branding */
    .main-header {
        background: linear-gradient(90deg, #C41E3A 0%, #A01729 100%);
        color: white;
        padding: 1rem 2rem;
        border-radius: 10px;
        margin-bottom: 2rem;
        text-align: center;
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
    }
    
    .main-header h1 {
        margin: 0;
        font-size: 2.5rem;
        font-weight: 700;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
    }
    
    .main-header .subtitle {
        font-size: 1.1rem;
        margin-top: 0.5rem;
        opacity: 0.9;
    }
    
    /* Form styling */
    .form-container {
        background: #F8F9FA;
        padding: 2rem;
        border-radius: 12px;
        border: 2px solid #E8E9EA;
        margin-bottom: 2rem;
    }
    
    /* Larger event type dropdown */
    div[data-testid="column"]:nth-child(2) .stSelectbox > div > div > div {
        min-height: 45px !important;
        font-size: 16px !important;
    }
    
    /* Make all form inputs larger and more readable */
    .stSelectbox > div > div > div,
    .stNumberInput > div > div > input,
    .stTextInput > div > div > input {
        font-size: 16px !important;
        padding: 12px !important;
        border-radius: 8px !important;
    }
    
    /* Success/error messages */
    .stSuccess {
        background-color: #D4EDDA;
        border-color: #C3E6CB;
        color: #155724;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #28A745;
    }
    
    .stError {
        background-color: #F8D7DA;
        border-color: #F5C6CB;
        color: #721C24;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #DC3545;
    }
    
    .stWarning {
        background-color: #FFF3CD;
        border-color: #FFEAA4;
        color: #856404;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #FFC107;
    }
    
    /* Primary button styling */
    .stButton > button[kind="primary"] {
        background: linear-gradient(90deg, #C41E3A 0%, #A01729 100%);
        border: none;
        padding: 12px 24px;
        font-size: 18px;
        font-weight: 600;
        border-radius: 8px;
        box-shadow: 0 3px 6px rgba(196, 30, 58, 0.3);
        transition: all 0.3s ease;
    }
    
    .stButton > button[kind="primary"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 12px rgba(196, 30, 58, 0.4);
    }
    
    /* Development mode banner */
    .dev-banner {
        background: linear-gradient(90deg, #17A2B8 0%, #138496 100%);
        color: white;
        padding: 0.75rem 1.5rem;
        border-radius: 8px;
        margin-bottom: 1rem;
        text-align: center;
        font-weight: 500;
    }
    
    /* Data tables */
    .dataframe {
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    /* Section dividers */
    hr {
        border: none;
        height: 2px;
        background: linear-gradient(90deg, #C41E3A 0%, transparent 100%);
        margin: 2rem 0;
    }
</style>
""", unsafe_allow_html=True)

token, user = require_auth()
store_id = get_user_store_id()
role = get_user_role()

if not store_id or not role:
    st.error("Missing user role/store information. Please contact admin.")
    st.stop()

# Main header with Seaway branding
st.markdown("""
<div class="main-header">
    <h1>🥩 Seaway Marketplace</h1>
    <div class="subtitle">Meat Shrink Tracking System</div>
</div>
""", unsafe_allow_html=True)

# Load dimensions
products = list_products(token)
event_types = list_event_types(token)

# Photo OCR Feature
st.markdown('<div class="form-container">', unsafe_allow_html=True)
st.subheader("📸 Quick Entry from Photo")

# Camera/Upload interface
col_photo1, col_photo2 = st.columns([2, 1])

with col_photo1:
    st.markdown("**Upload a photo of the meat label or scale tag:**")
    uploaded_file = st.file_uploader(
        "Choose image file",
        type=['png', 'jpg', 'jpeg'],
        help="Take a clear photo of the product label, scale tag, or barcode",
        label_visibility="collapsed"
    )
    
    # Camera input (mobile-friendly)
    camera_image = st.camera_input(
        "Or take a photo with your camera",
        help="Point camera at the meat label or scale tag",
        label_visibility="collapsed"
    )

# Process uploaded image
ocr_data = {}
if uploaded_file or camera_image:
    image_to_process = camera_image if camera_image else uploaded_file
    
    with st.spinner("🔍 Processing image and extracting data..."):
        ocr_result = process_uploaded_image(image_to_process)
    
    if ocr_result:
        with col_photo2:
            st.image(image_to_process, caption="Uploaded Image", width=200)
        
        # Show extraction results and get user corrections
        ocr_data = display_extraction_results(ocr_result)
        
        # Button to auto-populate the form
        if st.button("📝 Auto-Fill Form with Extracted Data", type="secondary", use_container_width=True):
            # Store OCR data in session state to populate form fields
            if ocr_data.get('weight_lbs'):
                st.session_state['ocr_prefill_weight'] = ocr_data['weight_lbs']
            if ocr_data.get('unit_price'):
                st.session_state['ocr_prefill_unit_price'] = ocr_data['unit_price']
            if ocr_data.get('unit_cost'):
                st.session_state['ocr_prefill_unit_cost'] = ocr_data['unit_cost']
            if ocr_data.get('category'):
                st.session_state['ocr_prefill_category'] = ocr_data['category']
            if ocr_data.get('product_name'):
                st.session_state['ocr_prefill_product_name'] = ocr_data['product_name']
            
            st.success("✅ Form auto-filled with extracted data! Review and adjust below.")
            st.rerun()

st.markdown('</div>', unsafe_allow_html=True)

# Manual Entry Form (with OCR pre-fill capability)
st.markdown('<div class="form-container">', unsafe_allow_html=True)
st.subheader("📝 Record Shrink Event")

# UI: Entry form with OCR pre-fill integration
col1, col2, col3 = st.columns([3, 2, 2])
with col1:
    prod_options = {f"{p['category']} • {p['cut_name']} • {p['product_type']}": p for p in products}
    
    # If OCR suggested a category and product name, try to find a match
    default_product_index = 0
    if st.session_state.get('ocr_prefill_category') and st.session_state.get('ocr_prefill_product_name'):
        ocr_category = st.session_state['ocr_prefill_category']
        ocr_product_name = st.session_state['ocr_prefill_product_name'].lower()
        
        # Find best matching product
        for i, (display_name, product) in enumerate(prod_options.items()):
            if (product['category'] == ocr_category and 
                any(word in product['cut_name'].lower() for word in ocr_product_name.split()[:3])):
                default_product_index = i
                break
    
    prod_label = st.selectbox(
        "🥩 Product", 
        list(prod_options.keys()), 
        index=default_product_index,
        key="fld_product_id", 
        help="Select the meat product (auto-suggested from photo if available)"
    )

with col2:
    ev = st.selectbox("📋 Event Type", event_types, key="fld_event_type", 
                     help="Select the reason for shrink")

with col3:
    # Use OCR weight if available
    default_weight = st.session_state.get('ocr_prefill_weight', 0.001)
    w = st.number_input("⚖️ Weight (lbs)", min_value=0.001, max_value=500.0, step=0.001, 
                       value=default_weight, format="%.3f", key="fld_weight_lbs", 
                       help="Enter weight in pounds (auto-filled from photo if detected)")

col4, col5, col6 = st.columns([2, 2, 3])
with col4:
    # Use OCR unit cost if available, otherwise try unit price as fallback
    default_cost = st.session_state.get('ocr_prefill_unit_cost') or st.session_state.get('ocr_prefill_unit_price', 0.0)
    uc = st.number_input("💰 Unit Cost ($)", min_value=0.0, max_value=999.9999, step=0.01, 
                        value=default_cost, format="%.2f", key="fld_unit_cost", 
                        help="Cost per pound (auto-filled from photo if detected)")

with col5:
    # Use OCR unit price if available
    default_price = st.session_state.get('ocr_prefill_unit_price', 0.0)
    up = st.number_input("🏷️ Unit Price ($)", min_value=0.0, max_value=999.9999, step=0.01, 
                        value=default_price, format="%.2f", key="fld_unit_price", 
                        help="Retail price per pound (auto-filled from photo if detected)")

with col6:
    # Better date/time layout
    st.write("📅 **Date & Time**")
    date_part = st.date_input("Date", value=datetime.now().date(), key="fld_date", label_visibility="collapsed")
    time_part = st.time_input("Time", value=datetime.now().time(), key="fld_time", label_visibility="collapsed")

notes = st.text_input("📝 Notes (optional)", key="fld_notes", help="Add any additional details")

st.markdown('</div>', unsafe_allow_html=True)

# Clear OCR session state after form is populated
if any(key.startswith('ocr_prefill_') for key in st.session_state.keys()):
    for key in list(st.session_state.keys()):
        if key.startswith('ocr_prefill_'):
            del st.session_state[key]

# Submit button with better styling
if st.button("🚀 Submit Shrink Event", type="primary", key="btn_submit_event", use_container_width=True):
    # Combine date and time
    dt = datetime.combine(date_part, time_part)
    
    # Get selected product details for category-specific validation
    selected_product = prod_options[prod_label]
    category = selected_product['category']
    
    # Validate with category-specific weight bands
    ok, msg = validate_weight(w, category)
    if not ok: 
        st.error(msg)
        st.stop()
    elif msg:  # Warning message
        st.warning(msg)
    
    ok, msg = validate_prices(uc, up, ev)
    if not ok: 
        st.error(msg)
        st.stop()
    
    dt_utc = (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    ok, msg = validate_datetime(dt_utc)
    if not ok: 
        if role in ("manager", "admin"):
            st.warning(f"{msg} (Manager override allowed)")
        else:
            st.error(msg)
            st.stop()

    payload = {
        "product_id": selected_product['id'],
        "store_id": store_id,
        "entered_by": user.id,
        "date_time": dt_utc.isoformat(),
        "event_type": ev,
        "weight_lbs": float(w),
        "unit_cost": float(uc),
        "unit_price": float(up),
        "notes": notes or None
    }
    try:
        row = insert_shrink_event(token, payload)
        st.success("✅ Shrink event recorded successfully!")
        st.session_state["fld_notes"] = ""
        st.rerun()
    except Exception as e:
        st.error(f"❌ Insert failed: {e}")

st.divider()
st.subheader("📊 Today's Events")
recent = list_recent_events(token, store_id=store_id, limit=50)
df = pd.DataFrame(recent)
if not df.empty:
    st.dataframe(df, use_container_width=True, height=400)
    
    # Correction workflow for lead+ roles
    if role in ("lead","manager","admin"):
        st.subheader("🔧 Create Correction")
        col_a, col_b, col_c = st.columns([1,2,1])
        with col_a:
            sel = st.selectbox("Event ID", options=[None]+df["id"].tolist())
        with col_b:
            reason = st.text_input("Correction reason", key="fld_correction_reason")
        with col_c:
            if st.button("Create Correction") and sel and reason:
                try:
                    create_correction(token, sel, reason)
                    st.success("✅ Correction created (append-only).")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Failed to create correction: {e}")
else:
    st.info("ℹ️ No entries recorded today. Start by recording your first shrink event above!")
