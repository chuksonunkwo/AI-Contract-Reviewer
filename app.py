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
    initial_sidebar_state="expanded"
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
GUMROAD_PRODUCT_ID = "xGeemEFxpMJUbG-jUVxIHg==" 

# ==========================================
# 🧠 INTELLIGENCE MODULES (The "Brain")
# ==========================================

# 1. CONTRACT TYPES (The Context Switch)
CONTRACT_TYPES = {
    "General / Universal": "Standard commercial agreement. Focus on term, termination, and general liability.",
    "Drilling Contract": "Oil & Gas specific. Focus on Rig Rates, Non-Productive Time (NPT), Knock-for-Knock Indemnities, and Pollution liability.",
    "EPC / EPCI Contract": "Engineering/Construction. Focus on Milestones, Completion Guarantees, Liquidated Damages (LDs), and Variation Orders.",
    "Master Service Agreement (MSA)": "Framework agreement. Focus on Call-Off mechanisms, Umbrella Liability, and Rate independence.",
    "SaaS / Software License": "Digital product. Focus on Uptime SLA, Data Privacy (GDPR/NDPR), IP Rights, and Auto-renewal.",
    "NDA / Confidentiality": "Secrecy agreement. Focus on 'Permitted Purpose', Duration of confidentiality, and Return of data.",
    "Technical Manpower": "Labor supply. Focus on Visa/Immigration compliance, Tax handling, and Personnel replacement rights."
}

# 2. JSON SCHEMA (The Output Structure)
SCHEMA_DEF = """
{
  "contract_meta": {
    "title": "Full Contract Title",
    "parties_involved": ["Party A", "Party B"],
    "contract_type_detected": "string",
    "risk_score_overall": "0-100",
    "risk_level": "High/Medium/Low",
    "bluf_verdict": "2-3 sentences. Bottom Line Up Front recommendation (Go/No-Go)."
  },
  "commercial_metrics": {
    "value_model": "e.g. Lumpsum / Unit Rate / Reimbursable",
    "payment_terms": "e.g. Net 30 Days",
    "contract_duration": "Start Date to End Date + Extensions",
    "termination_fees": "Cost to exit early"
  },
  "risk_map": {
    "liability_indemnity": { 
        "level": "High/Med/Low", 
        "summary": "Knock-for-knock, Caps, Consequential Loss status",
        "playbook_tip": "One sentence negotiation counter-measure"
    },
    "operational_performance": { 
        "level": "High/Med/Low", 
        "summary": "SLA, NPT (if drilling), KPIs, Milestones",
        "playbook_tip": "Negotiation tip"
    },
    "termination_rights": { 
        "level": "High/Med/Low", 
        "summary": "Termination for Convenience/Cause",
        "playbook_tip": "Negotiation tip"
    },
    "compliance_regulatory": { 
        "level": "High/Med/Low", 
        "summary": "Local Content (NOGICD), Sanctions, GDPR, Anti-Bribery",
        "playbook_tip": "Negotiation tip"
    }
  },
  "technical_deep_dive": {
    "scope_summary": ["Bullet 1", "Bullet 2"],
    "missing_clauses": ["List key clauses that are MISSING but should be there"]
  }
}
"""

# ==========================================
# 🎨 UI STYLING (Executive Dashboard)
# ==========================================
st.markdown("""
<style>
    .stApp { background-color: #ffffff; font-family: 'Helvetica Neue', sans-serif; }
    .dashboard-card {
        background-color: white; border: 1px solid #e5e7eb; border-radius: 8px;
        padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); height: 100%;
    }
    .brand-header { color: #d97706; font-size: 0.9rem; font-weight: 700; letter-spacing: 1px; text-transform: uppercase; }
    .bluf-box { background-color: #f8fafc; border-left: 5px solid #2563eb; padding: 15px; margin-bottom: 20px; }
    .metric-label { font-size: 0.75rem; color: #6b7280; text-transform: uppercase; font-weight: 600; margin-bottom: 5px; }
    .metric-value { font-size: 1.8rem; font-weight: 800; color: #111827; }
    .badge { padding: 4px 8px; border-radius: 4px; font-size: 0.7rem; font-weight: 700; text-transform: uppercase; }
    .badge-high { background: #fef2f2; color: #ef4444; border: 1px solid #fecaca; }
    .badge-med { background: #fffbeb; color: #f59e0b; border: 1px solid #fde68a; }
    .badge-low { background: #ecfdf5; color: #10b981; border: 1px solid #a7f3d0; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 🛠️ UTILITIES
# ==========================================

def check_gumroad_license(key):
    if not key: return False, "Enter Key"
    url = "https://api.gumroad.com/v2/licenses/verify"
    params = {"product_id": GUMROAD_PRODUCT_ID, "license_key": key, "increment_uses_count": "false"}
    try:
        response = requests.post(url, data=params)
        data = response.json()
        if data.get("success") and not data.get("purchase", {}).get("refunded"):
            return True, "Valid"
        return False, "Invalid Key"
    except: return False, "Connection Error"

def log_to_discord(message):
    if DISCORD_WEBHOOK:
        try: requests.post(DISCORD_WEBHOOK, json={"content": message})
        except: pass

def extract_text(file_obj):
    try:
        reader = PyPDF2.PdfReader(file_obj)
        text = ""
        for i in range(min(len(reader.pages), 60)): # 60 Page Safety Limit
            text += reader.pages[i].extract_text() + "\n"
        return text
    except: return None

# ==========================================
# 🧠 ANALYSIS ENGINE
# ==========================================
def run_analysis(text, contract_type, user_role):
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(ACTIVE_MODEL)
    
    # Dynamic Context Injection
    context_instruction = CONTRACT_TYPES.get(contract_type, "Standard commercial analysis.")
    role_instruction = f"You are reviewing this contract from the perspective of the {user_role}. Protect their interests."
    
    prompt = f"""
    ACT AS A SENIOR LEGAL STRATEGIST.
    {role_instruction}
    
    CONTEXT: The user has identified this as a: {contract_type}.
    SPECIFIC INSTRUCTION: {context_instruction}
    
    TASK: Perform a "Bottom Line Up Front" (BLUF) forensic analysis.
    
    OUTPUT SCHEMA (Strict JSON):
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
# 🖥️ APP
# ==========================================
def main():
    
    # --- SIDEBAR CONFIGURATION ---
    with st.sidebar:
        st.markdown("### 🔐 Secure Login")
        if "authenticated" not in st.session_state: st.session_state.authenticated = False
        
        if not st.session_state.authenticated:
            key = st.text_input("License Key", type="password")
            if st.button("Login"):
                valid, msg = check_gumroad_license(key)
                if valid:
                    st.session_state.authenticated = True
                    st.success("Access Granted")
                    st.rerun()
                else: st.error(msg)
            st.stop()
            
        st.success(f"🟢 Connected: {ACTIVE_MODEL}")
        
        st.markdown("---")
        st.markdown("### ⚙️ Analysis Parameters")
        
        # 1. Contract Selector (The Pivot)
        c_type = st.selectbox("Contract Type", list(CONTRACT_TYPES.keys()))
        
        # 2. Role Toggle (The Perspective)
        role = st.radio("My Role", ["Buyer / Client", "Seller / Contractor"], horizontal=True)
        
        uploaded_file = st.file_uploader("Upload Agreement (PDF)", type=["pdf"])
        
        if st.button("Logout"):
            st.session_state.authenticated = False
            st.rerun()

    # --- MAIN PAGE ---
    c1, c2 = st.columns([3, 1])
    with c1:
        st.markdown('<div class="brand-header">⚙️ CONTRACT ENGINE</div>', unsafe_allow_html=True)
        st.title("Strategic Assessment v1.0")
    
    if uploaded_file:
        if st.button("🚀 Run Forensic Analysis"):
            with st.spinner("⚙️ Scanning Document & Generating BLUF..."):
                log_to_discord(f"🚀 Analyzing: {uploaded_file.name} | Type: {c_type}")
                
                text = extract_text(uploaded_file)
                if text:
                    result = run_analysis(text, c_type, role)
                    if "error" not in result:
                        st.session_state.result = result
                        st.rerun()
                    else:
                        st.error(f"AI Error: {result['error']}")
                else:
                    st.error("Could not read PDF text.")

    # --- DASHBOARD RENDER ---
    if "result" in st.session_state:
        res = st.session_state.result
        meta = res.get("contract_meta", {})
        comm = res.get("commercial_metrics", {})
        risk = res.get("risk_map", {})
        tech = res.get("technical_deep_dive", {})

        # 1. BLUF BANNER
        st.markdown(f"""
        <div class="bluf-box">
            <h3 style="margin-top:0; color:#1e3a8a;">📢 BLUF: Executive Verdict</h3>
            <p style="font-size:1.1rem;">{meta.get('bluf_verdict', 'No verdict generated.')}</p>
        </div>
        """, unsafe_allow_html=True)

        # 2. METRIC CARDS
        col1, col2, col3, col4 = st.columns(4)
        score = meta.get("risk_score_overall", 0)
        color = "#ef4444" if int(score) > 70 else "#f59e0b" if int(score) > 40 else "#10b981"
        
        with col1:
            st.markdown(f"""<div class="dashboard-card"><div class="metric-label">Risk Score</div>
            <div class="metric-value" style="color:{color}">{score}/100</div>
            <small>{meta.get('risk_level')}</small></div>""", unsafe_allow_html=True)
            
        with col2:
            st.markdown(f"""<div class="dashboard-card"><div class="metric-label">Value Model</div>
            <div class="metric-value" style="font-size:1.4rem">{comm.get('value_model', 'N/A')[:15]}..</div>
            <small>{comm.get('payment_terms')}</small></div>""", unsafe_allow_html=True)
            
        with col3:
            st.markdown(f"""<div class="dashboard-card"><div class="metric-label">Duration</div>
            <div class="metric-value" style="font-size:1.4rem">{comm.get('contract_duration', 'N/A')[:15]}..</div>
            <small>Term + Options</small></div>""", unsafe_allow_html=True)
            
        with col4:
            st.markdown(f"""<div class="dashboard-card"><div class="metric-label">Exit Cost</div>
            <div class="metric-value" style="font-size:1.4rem">{comm.get('termination_fees', 'N/A')[:15]}..</div>
            <small>Termination Liability</small></div>""", unsafe_allow_html=True)

        st.markdown("---")

        # 3. STRATEGIC RISK MAP (Grid Layout)
        st.subheader("🛡️ Strategic Risk Map")
        r1, r2 = st.columns(2)
        
        def risk_card(title, data):
            lvl = data.get('level', 'Low')
            badge = "badge-high" if lvl == "High" else "badge-med" if lvl == "Medium" else "badge-low"
            return f"""
            <div class="dashboard-card" style="margin-bottom:20px;">
                <div style="display:flex; justify-content:space-between;">
                    <strong>{title}</strong>
                    <span class="badge {badge}">{lvl}</span>
                </div>
                <p style="margin-top:10px; font-size:0.9rem;">{data.get('summary')}</p>
                <div style="background:#f3f4f6; padding:8px; border-radius:4px; font-size:0.8rem; color:#4b5563;">
                    💡 <strong>Playbook:</strong> {data.get('playbook_tip')}
                </div>
            </div>
            """

        with r1:
            st.markdown(risk_card("LIABILITY & INDEMNITY", risk.get('liability_indemnity', {})), unsafe_allow_html=True)
            st.markdown(risk_card("OPERATIONAL / PERFORMANCE", risk.get('operational_performance', {})), unsafe_allow_html=True)
        with r2:
            st.markdown(risk_card("TERMINATION & EXIT", risk.get('termination_rights', {})), unsafe_allow_html=True)
            st.markdown(risk_card("COMPLIANCE & REGULATORY", risk.get('compliance_regulatory', {})), unsafe_allow_html=True)

        # 4. DEEP DIVE TABS
        st.markdown("### 🔍 Technical Deep Dive")
        t1, t2 = st.tabs(["Scope & Operations", "🚩 Missing Clauses"])
        
        with t1:
            for item in tech.get('scope_summary', []):
                st.markdown(f"- {item}")
        with t2:
            if tech.get('missing_clauses'):
                for item in tech.get('missing_clauses', []):
                    st.error(f"MISSING: {item}")
            else:
                st.success("No critical standard clauses appear to be missing.")

        # 5. DOWNLOAD
        st.markdown("---")
        json_str = json.dumps(res, indent=2)
        st.download_button("📥 Export Analysis Data (JSON)", json_str, "contract_analysis.json", "application/json")

if __name__ == "__main__":
    main()
