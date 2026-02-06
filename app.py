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
    page_title="Strategic Assessment", 
    layout="wide", 
    page_icon="⚖️",
    initial_sidebar_state="expanded"
)

# ⚡ CORE ENGINE: Reverted to 2.5 Pro as requested
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
# 🧠 INTELLIGENCE MODULES
# ==========================================

CONTRACT_TYPES = {
    "General / Commercial": "Focus on Term, Termination, Payment, and General Liability.",
    "Drilling / Rig Contract": "Focus on Day Rates, NPT (Non-Productive Time), Pollution Liability, and Knock-for-Knock.",
    "EPC / Construction": "Focus on Milestones, Completion Guarantees, LDs (Liquidated Damages), and HSE.",
    "SaaS / Technology": "Focus on Data Privacy (HSE equivalent), Uptime SLAs (Performance), and IP Rights.",
    "Master Service Agreement (MSA)": "Focus on Call-Off mechanisms, Umbrella Liability, and Rate fixation.",
    "Technical Manpower": "Focus on Personnel qualification, Visa/Immigration compliance, and Replacement rights."
}

# 2. JSON SCHEMA (Strict Structure)
SCHEMA_DEF = """
{
  "executive_summary": {
    "contract_title": "string",
    "counterparty": "string",
    "procurement_verdict": "2-3 sentences. A Senior Procurement Manager's Go/No-Go recommendation.",
    "risk_score": "0-100",
    "risk_level": "High/Medium/Low"
  },
  "commercial_terms": {
    "pricing_model": "e.g. Lumpsum / Unit Rates",
    "contract_value": "Estimated value or 'Call-Off'",
    "duration_details": "Term + Renewal Options",
    "payment_terms": "e.g. Net 45 Days"
  },
  "risk_analysis": {
    "legal_liability": { 
        "summary": "Indemnities, Caps on Liability, Consequential Loss waivers.",
        "risk_level": "High/Med/Low"
    },
    "hse_security": { 
        "summary": "Health/Safety/Environment risks OR Data Security/Privacy risks (depending on context).",
        "risk_level": "High/Med/Low"
    },
    "operational_performance": { 
        "summary": "SLAs, KPIs, Liquidated Damages (LDs), Non-Productive Time (NPT), Force Majeure.",
        "risk_level": "High/Med/Low"
    }
  },
  "technical_deep_dive": {
    "scope_summary": ["Bullet 1", "Bullet 2"],
    "missing_clauses": ["List only CRITICAL concepts that are completely absent (e.g. 'No Liability Cap'). Do not list Article numbers."]
  },
  "strategic_recommendations": [
    "Actionable Bullet 1 (Commercial Leverage)",
    "Actionable Bullet 2 (Legal Protection)",
    "Actionable Bullet 3 (Operational Safety)"
  ]
}
"""

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
        self.set_text_color(0, 51, 102) # Navy Blue
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

    # 1. Executive Summary
    exec_sum = data.get('executive_summary', {})
    pdf.set_font('Arial', 'B', 22)
    pdf.cell(0, 15, "Strategic Assessment", 0, 1, 'C')
    pdf.ln(5)
    
    # Verdict Box
    pdf.set_fill_color(230, 240, 255) # Light Blue
    pdf.rect(10, pdf.get_y(), 190, 35, 'F')
    pdf.set_font('Arial', 'B', 12)
    pdf.set_xy(15, pdf.get_y() + 5)
    pdf.cell(0, 10, f"VERDICT: {exec_sum.get('risk_level', 'N/A').upper()} RISK ({exec_sum.get('risk_score', '0')}/100)", 0, 1)
    pdf.set_font('Arial', '', 11)
    pdf.set_x(15)
    pdf.multi_cell(180, 6, exec_sum.get('procurement_verdict', ''))
    pdf.ln(20)

    # 2. Commercial Profile
    comm = data.get('commercial_terms', {})
    pdf.chapter_title("1. Commercial Profile")
    pdf.chapter_body(f"Model: {comm.get('pricing_model')}\nValue: {comm.get('contract_value')}\nDuration: {comm.get('duration_details')}\nPayment: {comm.get('payment_terms')}")

    # 3. Risk Analysis
    risk = data.get('risk_analysis', {})
    pdf.chapter_title("2. Risk Analysis")
    
    for key, val in risk.items():
        title = key.replace('_', ' ').upper()
        pdf.set_font('Arial', 'B', 11)
        pdf.cell(0, 8, f"{title} ({val.get('risk_level')})", 0, 1)
        pdf.set_font('Arial', '', 11)
        pdf.multi_cell(0, 6, val.get('summary', ''))
        pdf.ln(3)

    # 4. Strategic Recommendations
    pdf.chapter_title("3. Strategic Recommendations")
    recs = data.get('strategic_recommendations', [])
    for r in recs:
        pdf.set_font('Arial', 'B', 14)
        pdf.cell(10, 6, "-", 0, 0)
        pdf.set_font('Arial', '', 11)
        pdf.multi_cell(0, 6, r)
        pdf.ln(2)

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
        # 2.5 Pro has a huge context window, we can read more pages safely
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
    Your goal is to provide a "Strategic Assessment" for a C-Level executive.
    
    USER ROLE: {user_role} (Protect this side).
    CONTRACT TYPE: {contract_type}.
    SPECIFIC FOCUS: {context_instruction}
    
    TASK: Analyze the text and output strict JSON.
    
    1. **Procurement Verdict**: Give a clear Go/No-Go recommendation.
    2. **HSE & Security**: If Industrial, focus on Safety/Environment/Pollution. If Tech, focus on Data Security/Privacy.
    3. **Missing Clauses**: Be careful. Only list a clause as MISSING if a fundamental concept (like Liability Cap, Termination, or Payment Terms) is completely absent. Do NOT list specific Article numbers.
    
    OUTPUT SCHEMA:
    {SCHEMA_DEF}
    
    CONTRACT TEXT:
    {text[:150000]} 
    """
    # Note: Increased text limit to 150k chars for 2.5 Pro
    
    try:
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        return json.loads(response.text)
    except Exception as e:
        return {"error": str(e)}

# ==========================================
# 🖥️ UI / DASHBOARD
# ==========================================
def main():
    
    # CSS Styling
    st.markdown("""
        <style>
        .stApp { background-color: #f8fafc; font-family: 'Helvetica Neue', sans-serif; }
        .dashboard-card { background-color: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
        .metric-label { font-size: 0.8rem; color: #64748b; font-weight: 600; text-transform: uppercase; }
        .metric-value { font-size: 1.6rem; font-weight: 700; color: #0f172a; margin-top: 5px; }
        .verdict-box { background-color: #eff6ff; border-left: 4px solid #3b82f6; padding: 16px; margin-bottom: 24px; border-radius: 4px; }
        </style>
    """, unsafe_allow_html=True)

    # --- SIDEBAR (Security) ---
    with st.sidebar:
        st.title("⚖️ Contract Sentinel")
        
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
            
        st.markdown("---")
        st.subheader("Analysis Context")
        c_type = st.selectbox("Contract Type", list(CONTRACT_TYPES.keys()))
        role = st.radio("Perspective", ["Client / Buyer", "Contractor / Vendor"])
        uploaded_file = st.file_uploader("Upload Agreement (PDF)", type=["pdf"])
        
        if st.button("Logout"):
            st.session_state.authenticated = False
            st.rerun()

    # --- MAIN CONTENT ---
    st.title("Strategic Assessment")
    
    if uploaded_file:
        if st.button("🚀 Run Strategic Analysis"):
            with st.spinner(f"⚙️ Analyzing with {ACTIVE_MODEL}..."):
                text = extract_text(uploaded_file)
                if text:
                    log_to_discord(f"Analyzing {uploaded_file.name} as {c_type}")
                    result = run_analysis(text, c_type, role)
                    if "error" not in result:
                        st.session_state.result = result
                        st.rerun()
                    else: st.error(f"Analysis Failed: {result['error']}")

    if "result" in st.session_state:
        data = st.session_state.result
        
        # 1. EXECUTIVE VERDICT
        ex = data.get('executive_summary', {})
        st.markdown(f"""
        <div class="verdict-box">
            <h3 style="margin-top:0; color:#1e40af;">📝 Procurement Verdict</h3>
            <p style="font-size:1.1rem; color:#1e3a8a;">{ex.get('procurement_verdict')}</p>
        </div>
        """, unsafe_allow_html=True)

        # 2. METRICS ROW
        c1, c2, c3, c4 = st.columns(4)
        comm = data.get('commercial_terms', {})
        
        score = ex.get('risk_score', 0)
        color = "#ef4444" if int(score) > 70 else "#f59e0b" if int(score) > 40 else "#10b981"
        
        with c1: st.markdown(f"<div class='dashboard-card'><div class='metric-label'>Risk Score</div><div class='metric-value' style='color:{color}'>{score}/100</div></div>", unsafe_allow_html=True)
        with c2: st.markdown(f"<div class='dashboard-card'><div class='metric-label'>Model</div><div class='metric-value' style='font-size:1.2rem'>{comm.get('pricing_model', 'N/A')}</div></div>", unsafe_allow_html=True)
        with c3: st.markdown(f"<div class='dashboard-card'><div class='metric-label'>Term</div><div class='metric-value' style='font-size:1.2rem'>{comm.get('duration_details', 'N/A')}</div></div>", unsafe_allow_html=True)
        with c4: st.markdown(f"<div class='dashboard-card'><div class='metric-label'>Payment</div><div class='metric-value' style='font-size:1.2rem'>{comm.get('payment_terms', 'N/A')}</div></div>", unsafe_allow_html=True)

        st.markdown("---")

        # 3. DETAILED ANALYSIS TABS
        t1, t2, t3, t4, t5 = st.tabs(["⚖️ Legal Liability", "⛑️ HSE & Security", "⚙️ Ops & Performance", "💡 Recommendations", "🔍 Missing Clauses"])
        
        risk = data.get('risk_analysis', {})
        tech = data.get('technical_deep_dive', {})
        
        with t1:
            r = risk.get('legal_liability', {})
            st.subheader(f"Legal Liability ({r.get('risk_level')})")
            st.write(r.get('summary'))
            
        with t2:
            r = risk.get('hse_security', {})
            st.subheader(f"HSE / Data Security ({r.get('risk_level')})")
            st.write(r.get('summary'))
            
        with t3:
            r = risk.get('operational_performance', {})
            st.subheader(f"Performance & Operations ({r.get('risk_level')})")
            st.write(r.get('summary'))
            
        with t4:
            st.subheader("Strategic Recommendations")
            for rec in data.get('strategic_recommendations', []):
                st.info(rec)

        with t5:
            if tech.get('missing_clauses'):
                for item in tech.get('missing_clauses', []):
                    st.warning(f"⚠️ {item}")
            else:
                st.success("No critical missing clauses detected.")

        # 4. PDF DOWNLOAD
        st.markdown("---")
        if st.button("📄 Generate PDF Report"):
            pdf_bytes = generate_pdf(data)
            st.download_button("📥 Download Strategic Assessment (PDF)", pdf_bytes, "Strategic_Assessment.pdf", "application/pdf")

if __name__ == "__main__":
    main()
