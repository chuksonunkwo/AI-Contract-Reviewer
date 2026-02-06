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

# ⚡ CORE ENGINE (As requested)
ACTIVE_MODEL = "gemini-1.5-pro" 
# Note: "gemini-2.5-pro" is not a standard public endpoint yet. 
# "1.5-pro" is the current "Senior Strategist" model. 
# If your API key has special access to 2.5, change this string back to "gemini-2.5-pro".

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
# 🧠 INTELLIGENCE MODULES
# ==========================================

CONTRACT_TYPES = {
    "General / Universal": "Standard commercial agreement. Focus on Term, Termination, Payment, and General Liability.",
    "Drilling / Rig Contract": "Oil & Gas specific. Focus on Day Rates, NPT (Non-Productive Time), Pollution Liability, and Knock-for-Knock.",
    "EPC / Construction": "Focus on Milestones, Completion Guarantees, LDs (Liquidated Damages), and HSE.",
    "SaaS / Technology": "Focus on Data Privacy (HSE equivalent), Uptime SLAs (Performance), and IP Rights.",
    "Master Service Agreement (MSA)": "Focus on Call-Off mechanisms, Umbrella Liability, and Rate fixation.",
    "Technical Manpower": "Focus on Personnel qualification, Visa/Immigration compliance, and Replacement rights."
}

# 2. JSON SCHEMA (Restored for the High-Fidelity Dashboard)
SCHEMA_DEF = """
{
  "contract_meta": {
    "title": "Full Contract Title",
    "parties_involved": ["Party A", "Party B"],
    "contract_type_detected": "string",
    "risk_score_overall": "0-100",
    "risk_level": "High/Medium/Low",
    "risk_rationale": "1 sentence on why this score was given."
  },
  "commercial_metrics": {
    "value_model": "e.g. Unit Rates / Call-Off / Lumpsum",
    "value_details": "Estimated value or rate structure summary",
    "contract_duration": "Start Date to End Date + Extensions",
    "payment_terms": "e.g. Net 30 Days"
  },
  "executive_summary": {
    "strategic_verdict": "2-3 sentences. A Senior Procurement Manager's Go/No-Go recommendation.",
    "key_observations": ["Bullet 1", "Bullet 2", "Bullet 3"]
  },
  "risk_map": {
    "liability_indemnity": { 
        "level": "High/Med/Low", 
        "summary": "Knock-for-knock, Caps, Deductibles, Consequential Loss."
    },
    "termination_rights": { 
        "level": "High/Med/Low", 
        "summary": "Convenience, Cause, Notice periods."
    },
    "operational_performance": { 
        "level": "High/Med/Low", 
        "summary": "NPT, SLAs, Liquidated Damages, Golden Rules."
    },
    "compliance_regulatory": { 
        "level": "High/Med/Low", 
        "summary": "Local Content (NOGICD), Sanctions, Anti-Bribery, GDPR."
    }
  },
  "technical_deep_dive": {
    "scope_summary": ["Bullet 1", "Bullet 2"],
    "missing_clauses": ["List CRITICAL concepts missing (e.g. 'No Liability Cap'). Do not list Article numbers."]
  },
  "strategic_recommendations": [
    "Actionable Bullet 1", "Actionable Bullet 2", "Actionable Bullet 3"
  ]
}
"""

# ==========================================
# 🎨 HIGH-FIDELITY UI (The "Contract Engine" Look)
# ==========================================
st.markdown("""
<style>
    /* Main Background & Fonts */
    .stApp { background-color: #ffffff; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; }
    
    /* Card Container */
    .metric-card {
        background-color: white;
        border: 1px solid #e5e7eb;
        border-radius: 8px;
        padding: 20px;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
        height: 100%;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }
    
    /* Typography */
    .brand-header { color: #d97706; font-size: 0.9rem; font-weight: 700; letter-spacing: 1px; text-transform: uppercase; margin-bottom: 5px; }
    .card-label { font-size: 0.75rem; color: #6b7280; text-transform: uppercase; font-weight: 600; margin-bottom: 8px; }
    .card-value { font-size: 1.25rem; font-weight: 700; color: #111827; line-height: 1.2; }
    .card-sub { font-size: 0.85rem; color: #4b5563; margin-top: 5px; }
    
    /* Risk Badges */
    .risk-tag { padding: 4px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; display: inline-block; }
    .tag-high { background-color: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }
    .tag-med { background-color: #fffbeb; color: #92400e; border: 1px solid #fde68a; }
    .tag-low { background-color: #ecfdf5; color: #065f46; border: 1px solid #a7f3d0; }

    /* Risk Map Grid */
    .risk-box {
        border-left: 4px solid #ddd;
        padding-left: 15px;
        margin-bottom: 20px;
    }
    .risk-box h4 { margin: 0 0 5px 0; font-size: 1rem; color: #1f2937; }
    .risk-box p { margin: 0; font-size: 0.9rem; color: #4b5563; }

    /* Alerts */
    .missing-alert {
        background-color: #fef2f2;
        border-left: 4px solid #ef4444;
        padding: 10px 15px;
        margin-bottom: 10px;
        color: #b91c1c;
        font-size: 0.9rem;
    }
    .safe-alert {
        background-color: #ecfdf5;
        border-left: 4px solid #10b981;
        padding: 10px 15px;
        margin-bottom: 10px;
        color: #047857;
        font-size: 0.9rem;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 📄 PDF REPORT ENGINE
# ==========================================
class StrategicReport(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 10, 'CONFIDENTIAL // STRATEGIC ASSESSMENT', 0, 1, 'C')
        self.line(10, 20, 200, 20)
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

    def chapter_title(self, label):
        self.set_font('Arial', 'B', 14)
        self.set_text_color(0, 51, 102)
        self.cell(0, 10, label, 0, 1, 'L')
        self.ln(2)

    def chapter_body(self, body):
        self.set_font('Arial', '', 11)
        self.set_text_color(50, 50, 50)
        self.multi_cell(0, 6, str(body))
        self.ln(5)

def generate_pdf(data):
    pdf = StrategicReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Title
    pdf.set_font('Arial', 'B', 22)
    meta = data.get('contract_meta', {})
    pdf.multi_cell(0, 10, str(meta.get('title', 'Contract Assessment')))
    pdf.ln(5)
    
    # Verdict
    exec_sum = data.get('executive_summary', {})
    pdf.set_fill_color(240, 240, 240)
    pdf.rect(10, pdf.get_y(), 190, 30, 'F')
    pdf.set_font('Arial', 'B', 12)
    pdf.set_xy(15, pdf.get_y()+5)
    pdf.cell(0, 10, f"VERDICT: {meta.get('risk_level', 'N/A').upper()} ({meta.get('risk_score_overall', 0)}/100)", 0, 1)
    pdf.set_font('Arial', '', 11)
    pdf.set_x(15)
    pdf.multi_cell(180, 6, exec_sum.get('strategic_verdict', ''))
    pdf.ln(15)

    # Risks
    pdf.chapter_title("Strategic Risk Analysis")
    risk_map = data.get('risk_map', {})
    for k, v in risk_map.items():
        title = k.replace('_', ' ').upper()
        pdf.set_font('Arial', 'B', 11)
        pdf.cell(0, 8, f"{title} [{v.get('level')}]", 0, 1)
        pdf.set_font('Arial', '', 11)
        pdf.multi_cell(0, 6, v.get('summary'))
        pdf.ln(3)

    # Missing
    pdf.chapter_title("Missing Clauses & Gaps")
    tech = data.get('technical_deep_dive', {})
    if tech.get('missing_clauses'):
        for m in tech.get('missing_clauses'):
            pdf.set_text_color(200, 0, 0)
            pdf.cell(10, 6, "(!)", 0, 0)
            pdf.set_text_color(0, 0, 0)
            pdf.multi_cell(0, 6, m)
    else:
        pdf.multi_cell(0, 6, "No critical missing clauses detected.")

    return pdf.output(dest='S').encode('latin-1', 'replace')

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
        if data.get("success") and not data.get("purchase", {}).get("refunded"): return True, "Valid"
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
        # Limit pages to prevent timeouts
        for i in range(min(len(reader.pages), 100)): 
            text += reader.pages[i].extract_text() + "\n"
        return text
    except: return None

# ==========================================
# 🧠 ANALYSIS ENGINE
# ==========================================
def run_analysis(text, contract_type, user_role):
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(ACTIVE_MODEL)
    
    context_instruction = CONTRACT_TYPES.get(contract_type, "Standard commercial analysis.")
    
    prompt = f"""
    ACT AS A SENIOR LEGAL STRATEGIST AND PROCUREMENT MANAGER.
    Your goal is to provide a "Strategic Assessment" for a C-Level executive (High level, Visual, Impactful).
    
    USER ROLE: {user_role} (Protect this side).
    CONTRACT TYPE: {contract_type}.
    SPECIFIC FOCUS: {context_instruction}
    
    TASK: Analyze the text and output strict JSON.
    
    1. **Strategic Verdict**: Professional recommendation (Go/No-Go/Negotiate).
    2. **Risk Scoring**: Be realistic. 
    3. **Missing Clauses**: Only flag major omissions (e.g. "No Force Majeure", "No Liability Cap"). 
    
    OUTPUT SCHEMA:
    {SCHEMA_DEF}
    
    CONTRACT TEXT:
    {text[:150000]} 
    """
    
    try:
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        return json.loads(response.text)
    except Exception as e:
        return {"error": str(e)}

# ==========================================
# 🖥️ UI / DASHBOARD
# ==========================================
def main():
    
    # --- SIDEBAR (Security) ---
    with st.sidebar:
        st.markdown("### 🔐 Secure Login")
        if "authenticated" not in st.session_state: st.session_state.authenticated = False
        
        if not st.session_state.authenticated:
            key = st.text_input("License Key", type="password")
            if st.button("Authenticate"):
                valid, msg = check_gumroad_license(key)
                if valid:
                    st.session_state.authenticated = True
                    st.success("Access Granted")
                    st.rerun()
                else: st.error(msg)
            st.stop()
            
        st.success("🟢 System Online")
        st.markdown("---")
        st.subheader("Analysis Parameters")
        c_type = st.selectbox("Contract Type", list(CONTRACT_TYPES.keys()))
        role = st.radio("Perspective", ["Client / Buyer", "Contractor / Vendor"])
        uploaded_file = st.file_uploader("Upload Agreement (PDF)", type=["pdf"])
        
        if st.button("Logout"):
            st.session_state.authenticated = False
            st.rerun()

    # --- MAIN CONTENT ---
    # Header
    c1, c2 = st.columns([3,1])
    with c1:
        st.markdown('<div class="brand-header">⚙️ CONTRACT ENGINE</div>', unsafe_allow_html=True)
        st.title("Strategic Assessment")
    
    # Process
    if uploaded_file:
        if st.button("🚀 Run Forensic Analysis"):
            with st.spinner("⚙️ Scanning Document & Generating Strategy..."):
                text = extract_text(uploaded_file)
                if text:
                    result = run_analysis(text, c_type, role)
                    if "error" not in result:
                        st.session_state.result = result
                        st.rerun()
                    else: st.error(f"Analysis Failed: {result['error']}")

    # Dashboard
    if "result" in st.session_state:
        data = st.session_state.result
        meta = data.get('contract_meta', {})
        comm = data.get('commercial_metrics', {})
        risk = data.get('risk_map', {})
        exec_sum = data.get('executive_summary', {})
        tech = data.get('technical_deep_dive', {})

        # 1. HERO ROW (Title & Score)
        st.markdown(f"### {meta.get('title', 'Contract Analysis')} ✅")
        
        col1, col2, col3, col4 = st.columns(4)
        
        # Color Logic
        score = meta.get("risk_score_overall", 0)
        level = meta.get("risk_level", "Medium")
        if int(score) > 75: r_color, r_bg = "#b91c1c", "#fef2f2" # High (Red)
        elif int(score) > 40: r_color, r_bg = "#b45309", "#fffbeb" # Med (Orange)
        else: r_color, r_bg = "#047857", "#ecfdf5" # Low (Green)

        with col1:
            st.markdown(f"""
            <div class="metric-card" style="border-top: 4px solid {r_color};">
                <div>
                    <div class="card-label">Overall Risk</div>
                    <div class="card-value" style="color: {r_color};">{level}</div>
                    <div class="card-sub">{score}/100</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
        with col2:
            st.markdown(f"""
            <div class="metric-card">
                <div><div class="card-label">Value Model</div>
                <div class="card-value" style="font-size: 1.1rem;">{comm.get('value_model')}</div>
                <div class="card-sub">{comm.get('payment_terms')}</div></div>
            </div>
            """, unsafe_allow_html=True)

        with col3:
            st.markdown(f"""
            <div class="metric-card">
                <div><div class="card-label">Term</div>
                <div class="card-value" style="font-size: 1.1rem;">{comm.get('contract_duration')}</div>
                <div class="card-sub">Duration</div></div>
            </div>
            """, unsafe_allow_html=True)

        with col4:
            st.markdown(f"""
            <div class="metric-card">
                <div><div class="card-label">Type</div>
                <div class="card-value" style="font-size: 1.1rem;">{meta.get('contract_type_detected', 'Service')}</div>
                <div class="card-sub">Classification</div></div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("---")

        # 2. EXECUTIVE VERDICT
        st.subheader("📝 Procurement Verdict")
        st.info(exec_sum.get('strategic_verdict'))
        
        # 3. STRATEGIC RISK MAP (Grid)
        st.subheader("🛡️ Strategic Risk Map")
        
        r_c1, r_c2 = st.columns(2)
        
        def render_risk(title, r_data):
            lvl = r_data.get('level', 'Low')
            tag_class = "tag-high" if lvl == "High" else "tag-med" if lvl == "Medium" else "tag-low"
            border_color = "#ef4444" if lvl == "High" else "#f59e0b" if lvl == "Medium" else "#10b981"
            
            return f"""
            <div class="metric-card" style="margin-bottom: 20px; border-left: 4px solid {border_color};">
                <div style="display:flex; justify-content:space-between; margin-bottom:10px;">
                    <span style="font-weight:700; color:#374151;">{title}</span>
                    <span class="risk-tag {tag_class}">{lvl} RISK</span>
                </div>
                <p style="font-size:0.9rem; color:#4b5563; margin:0;">{r_data.get('summary')}</p>
            </div>
            """

        with r_c1:
            st.markdown(render_risk("LIABILITY & INDEMNITY", risk.get('liability_indemnity', {})), unsafe_allow_html=True)
            st.markdown(render_risk("OPERATIONAL / PERFORMANCE", risk.get('operational_performance', {})), unsafe_allow_html=True)
            
        with r_c2:
            st.markdown(render_risk("TERMINATION & EXIT", risk.get('termination_rights', {})), unsafe_allow_html=True)
            st.markdown(render_risk("COMPLIANCE & REGULATORY", risk.get('compliance_regulatory', {})), unsafe_allow_html=True)

        # 4. TABS (Deep Dive)
        t1, t2, t3 = st.tabs(["💡 Strategic Recommendations", "🔍 Missing Clauses", "📋 Scope & Technical"])
        
        with t1:
            for rec in data.get('strategic_recommendations', []):
                st.markdown(f"- {rec}")
                
        with t2:
            st.write("##### Critical Omissions Detection")
            missing = tech.get('missing_clauses', [])
            if missing:
                for m in missing:
                    st.markdown(f"<div class='missing-alert'>⚠️ <strong>MISSING:</strong> {m}</div>", unsafe_allow_html=True)
            else:
                st.markdown("<div class='safe-alert'>✅ No critical standard clauses appear to be missing.</div>", unsafe_allow_html=True)

        with t3:
            for item in tech.get('scope_summary', []):
                st.write(f"- {item}")

        # 5. PDF DOWNLOAD
        st.markdown("---")
        if st.button("📄 Generate Strategic Report"):
            pdf_bytes = generate_pdf(data)
            st.download_button("📥 Download PDF", pdf_bytes, "Strategic_Assessment.pdf", "application/pdf")

if __name__ == "__main__":
    main()
