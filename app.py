import streamlit as st
import google.generativeai as genai
import json
import os
import requests
import io
import time
from fpdf import FPDF
import PyPDF2
from google.api_core import exceptions

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
st.set_page_config(
    page_title="Contract Engine", 
    layout="wide", 
    page_icon="⚙️",
    initial_sidebar_state="collapsed"
)

APP_VERSION = "1.0 (Production)"
ACTIVE_MODEL = "gemini-2.5-pro"

# 1. CREDENTIALS
try:
    API_KEY = os.environ.get("GEMINI_API_KEY")
    if not API_KEY:
        API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    API_KEY = None

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL")
# Replace this with your actual Gumroad Product ID
GUMROAD_PRODUCT_ID = "xGeemEFxpMJUbG-jUVxIHg==" 

# ==========================================
# 🎨 UI STYLING (THE "CONTRACT ENGINE" LOOK)
# ==========================================
# This CSS matches the screenshots you provided (Cards, Badges, Clean Fonts)
st.markdown("""
<style>
    /* Main Background */
    .stApp { background-color: #ffffff; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; }
    
    /* Card Container */
    .dashboard-card {
        background-color: white;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 20px;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
        height: 100%;
    }
    
    /* Headings */
    h1, h2, h3 { color: #111827; font-weight: 700; }
    .brand-header { color: #d97706; font-size: 0.9rem; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase; margin-bottom: 5px; }
    .section-header { font-size: 1.5rem; color: #1f2937; margin-top: 30px; margin-bottom: 15px; border-bottom: 1px solid #e5e7eb; padding-bottom: 10px; }

    /* Metric Values */
    .metric-label { font-size: 0.75rem; color: #6b7280; text-transform: uppercase; font-weight: 600; letter-spacing: 0.5px; margin-bottom: 5px; }
    .metric-value-big { font-size: 2rem; font-weight: 800; color: #111827; }
    .metric-subtext { font-size: 0.85rem; color: #6b7280; margin-top: 5px; }

    /* Risk Badges */
    .badge { padding: 4px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; display: inline-block; }
    .badge-high { background-color: #fef2f2; color: #ef4444; border: 1px solid #fecaca; }
    .badge-med { background-color: #fffbeb; color: #f59e0b; border: 1px solid #fde68a; }
    .badge-low { background-color: #ecfdf5; color: #10b981; border: 1px solid #a7f3d0; }

    /* Text */
    .content-text { font-size: 0.95rem; color: #374151; line-height: 1.6; }
    
    /* Layout Helpers */
    .risk-map-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 30px; }
    .risk-item { border-left: 4px solid #d1d5db; padding-left: 15px; margin-bottom: 15px; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 🛠️ UTILITIES (Gumroad, Discord, etc.)
# ==========================================

def check_gumroad_license(key):
    """Verifies the license key with Gumroad API."""
    # BYPASS MODE: If no key entered, block access.
    # If you want a free trial, you can modify logic here.
    if not key: return False, "Enter Key"
    
    url = "https://api.gumroad.com/v2/licenses/verify"
    params = {"product_id": GUMROAD_PRODUCT_ID, "license_key": key, "increment_uses_count": "false"}
    try:
        response = requests.post(url, data=params)
        data = response.json()
        if data.get("success") and not data.get("purchase", {}).get("refunded"):
            return True, "Valid"
        return False, "Invalid Key"
    except:
        return False, "Connection Error"

def log_to_discord(message):
    """Sends logs to your Discord channel."""
    if DISCORD_WEBHOOK:
        try:
            requests.post(DISCORD_WEBHOOK, json={"content": message})
        except: pass

def extract_text_safe(file_obj):
    """Reads PDF text safely using PyPDF2."""
    try:
        pdf_reader = PyPDF2.PdfReader(file_obj)
        text = ""
        # Limit to first 60 pages to prevent token overflow
        for i in range(min(len(pdf_reader.pages), 60)):
            page = pdf_reader.pages[i]
            if page.extract_text():
                text += page.extract_text() + "\n"
        return text
    except Exception as e:
        return f"Error reading PDF: {e}"

# ==========================================
# 🧠 AI ENGINE (Prompt Engineering)
# ==========================================
# This schema matches your new dashboard layout
SCHEMA_DEF = """
{
  "contract_meta": {
    "title": "Full Contract Title",
    "parties_involved": ["Party A", "Party B"],
    "contract_type": "e.g. Master Service Agreement",
    "risk_score_overall": "0-100",
    "risk_level": "High/Medium/Low",
    "risk_rationale": "1 sentence summary"
  },
  "commercial_metrics": {
    "value_model": "e.g. Unit Rates / Call-Off",
    "value_details": "Short summary of value/rates",
    "term_duration": "e.g. 3 Years + Options",
    "term_details": "Specific dates if found"
  },
  "risk_map": {
    "liability": { "level": "High/Medium/Low", "summary": "Summary of indemnity/liability" },
    "termination": { "level": "High/Medium/Low", "summary": "Summary of termination rights" },
    "operational": { "level": "High/Medium/Low", "summary": "Summary of operational/NPT risks" },
    "compliance": { "level": "High/Medium/Low", "summary": "Summary of local content/sanctions" }
  },
  "deep_dive": {
    "executive_summary": ["Bullet 1", "Bullet 2", "Bullet 3"],
    "commercial_analysis": ["Bullet 1", "Bullet 2"],
    "technical_scope": ["Bullet 1", "Bullet 2"],
    "recommendations": ["Rec 1", "Rec 2"]
  }
}
"""

def analyze_contract(text):
    """Sends text to Gemini 2.5 Pro."""
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(ACTIVE_MODEL)
    
    prompt = f"""
    ACT AS A SENIOR CONTRACT ANALYST (Oil & Gas Specialist).
    Analyze this contract text.
    
    Output strictly VALID JSON using this schema:
    {SCHEMA_DEF}
    
    CONTRACT TEXT:
    {text[:75000]}
    """
    
    try:
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        return json.loads(response.text)
    except Exception as e:
        return {"error": str(e)}

# ==========================================
# 🖥️ MAIN APPLICATION FLOW
# ==========================================
def main():
    
    # --- 1. SIDEBAR (Login & Upload) ---
    with st.sidebar:
        st.markdown("### 🔐 Secure Login")
        
        # Check Session State for Login
        if "authenticated" not in st.session_state:
            st.session_state.authenticated = False

        if not st.session_state.authenticated:
            license_key = st.text_input("License Key", type="password")
            if st.button("Login"):
                valid, msg = check_gumroad_license(license_key)
                if valid:
                    st.session_state.authenticated = True
                    st.session_state.license_key = license_key
                    st.success("Access Granted")
                    st.rerun()
                else:
                    st.error(msg)
            st.info("Enter your Gumroad key to access the engine.")
            st.stop() # Stop here if not logged in
        
        # If Logged In:
        st.success("🟢 System Online")
        uploaded_file = st.file_uploader("Upload Agreement", type=["pdf"])
        
        if st.button("Logout"):
            st.session_state.authenticated = False
            st.rerun()

    # --- 2. HEADER ---
    c1, c2 = st.columns([3, 1])
    with c1:
        st.markdown('<div class="brand-header">⚙️ CONTRACT ENGINE</div>', unsafe_allow_html=True)
        st.markdown('<h1>Oil & Gas Edition</h1>', unsafe_allow_html=True)
    
    # --- 3. ANALYSIS LOGIC ---
    if uploaded_file:
        if "analysis_result" not in st.session_state or st.session_state.get("last_file") != uploaded_file.name:
            if st.button("🚀 Analyze Contract"):
                with st.spinner("⚙️ Engine Running: extracting text, analyzing clauses..."):
                    
                    # Log Start
                    log_to_discord(f"🚀 Started analysis: {uploaded_file.name}")
                    
                    # 1. Read PDF
                    text = extract_text_safe(uploaded_file)
                    
                    # 2. Analyze
                    result = analyze_contract(text)
                    
                    if "error" in result:
                        st.error(f"Analysis Failed: {result['error']}")
                        log_to_discord(f"❌ Failed: {result['error']}")
                    else:
                        st.session_state.analysis_result = result
                        st.session_state.last_file = uploaded_file.name
                        log_to_discord(f"✅ Success: {uploaded_file.name} (Score: {result['contract_meta']['risk_score_overall']})")
                        st.rerun()
    
    # --- 4. DASHBOARD RENDER ---
    if "analysis_result" in st.session_state:
        res = st.session_state.analysis_result
        meta = res.get("contract_meta", {})
        comm = res.get("commercial_metrics", {})
        risk = res.get("risk_map", {})
        deep = res.get("deep_dive", {})

        # Header Title
        st.markdown(f"## {meta.get('title', 'Contract Analysis')} ✅")
        st.markdown("---")

        # ROW 1: METRIC CARDS
        col1, col2, col3, col4 = st.columns(4)
        
        # Card 1: Risk Score
        score = meta.get("risk_score_overall", "0")
        score_color = "#ef4444" if int(score) > 70 else "#f59e0b" if int(score) > 40 else "#10b981"
        
        with col1:
            st.markdown(f"""
            <div class="dashboard-card">
                <div class="metric-label">Overall Risk Rating</div>
                <div class="metric-value-big" style="color: {score_color}">{meta.get('risk_level', 'Unknown')}</div>
                <div class="metric-subtext">Score: {score}/100</div>
                <div class="content-text" style="font-size: 0.8rem; margin-top: 10px;">{meta.get('risk_rationale', '')}</div>
            </div>
            """, unsafe_allow_html=True)

        # Card 2: Value
        with col2:
            st.markdown(f"""
            <div class="dashboard-card">
                <div class="metric-label">Contract Value</div>
                <div class="metric-value-big" style="font-size: 1.4rem;">{comm.get('value_model', 'N/A')}</div>
                <div class="content-text" style="font-size: 0.85rem; margin-top: 10px;">{comm.get('value_details', '')}</div>
            </div>
            """, unsafe_allow_html=True)

        # Card 3: Term
        with col3:
            st.markdown(f"""
            <div class="dashboard-card">
                <div class="metric-label">Term & Duration</div>
                <div class="metric-value-big" style="font-size: 1.4rem;">{comm.get('term_duration', 'N/A')}</div>
                <div class="content-text" style="font-size: 0.85rem; margin-top: 10px;">{comm.get('term_details', '')}</div>
            </div>
            """, unsafe_allow_html=True)

        # Card 4: Type
        with col4:
            st.markdown(f"""
            <div class="dashboard-card">
                <div class="metric-label">Contract Type</div>
                <div class="metric-value-big" style="font-size: 1.4rem;">{meta.get('contract_type', 'Service Agmt')}</div>
                <div class="content-text" style="font-size: 0.85rem; margin-top: 10px;">Parties: {', '.join(meta.get('parties_involved', []))}</div>
            </div>
            """, unsafe_allow_html=True)

        # ROW 2: RISK MAP
        st.markdown('<div class="section-header">🛡️ Strategic Risk Map</div>', unsafe_allow_html=True)
        
        r1, r2 = st.columns(2)
        
        def render_risk_card(title, data):
            level = data.get('level', 'Low')
            badge_class = "badge-high" if level == "High" else "badge-med" if level == "Medium" else "badge-low"
            return f"""
            <div class="dashboard-card" style="margin-bottom: 20px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                    <div class="metric-label" style="font-size: 0.9rem;">{title}</div>
                    <span class="badge {badge_class}">{level} RISK</span>
                </div>
                <div class="content-text">{data.get('summary', 'No data')}</div>
            </div>
            """

        with r1:
            st.markdown(render_risk_card("LIABILITY & INDEMNITY", risk.get('liability', {})), unsafe_allow_html=True)
            st.markdown(render_risk_card("OPERATIONAL / PERFORMANCE", risk.get('operational', {})), unsafe_allow_html=True)
            
        with r2:
            st.markdown(render_risk_card("TERMINATION & SUSPENSION", risk.get('termination', {})), unsafe_allow_html=True)
            st.markdown(render_risk_card("COMPLIANCE & REGULATORY", risk.get('compliance', {})), unsafe_allow_html=True)

        # ROW 3: DETAILED TABS
        st.markdown('<div class="section-header">📄 Comprehensive Report</div>', unsafe_allow_html=True)
        
        tab1, tab2, tab3 = st.tabs(["Executive Summary", "Commercial & Scope", "Strategic Recommendations"])
        
        with tab1:
            st.write("#### Executive Summary")
            for item in deep.get('executive_summary', []):
                st.markdown(f"- {item}")
                
        with tab2:
            st.write("#### Commercial & Financial Profile")
            for item in deep.get('commercial_analysis', []):
                st.markdown(f"- {item}")
            st.write("#### Scope of Work")
            for item in deep.get('technical_scope', []):
                st.markdown(f"- {item}")

        with tab3:
            st.write("#### Strategic Recommendations")
            for item in deep.get('recommendations', []):
                st.info(item)
                
        # DOWNLOAD
        st.markdown("---")
        json_str = json.dumps(res, indent=2)
        st.download_button("📥 Export Analysis (JSON)", json_str, "contract_analysis.json", "application/json")

if __name__ == "__main__":
    main()
