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
    page_title="Contract Intelligence", 
    layout="wide", 
    page_icon="⚖️",
    initial_sidebar_state="collapsed"
)

# ⚡ CORE ENGINE: Gemini 1.5 Pro (The Senior Strategist)
ACTIVE_MODEL = "gemini-1.5-pro"

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
# 🧠 INTELLIGENCE SCHEMA (The New Architecture)
# ==========================================

# Defines the specific output structure for the Dashboard
SCHEMA_DEF = """
{
  "contractDetails": {
    "title": "Official Title of Agreement",
    "parties": ["Party A", "Party B"]
  },
  "overallRisk": {
    "score": 0-100,
    "level": "High/Medium/Low",
    "rationale": "One sentence synthesis of the primary risk driver."
  },
  "keyCommercials": {
    "value": "Total Contract Value or Rate Structure",
    "duration": "Effective Date to End Date + Extensions",
    "contractType": "e.g. Drilling, EPC, MSA, SaaS"
  },
  "executiveSummary": [
    "- **Headline**: Brief synthesis of point 1.",
    "- **Headline**: Brief synthesis of point 2.",
    "- **Headline**: Brief synthesis of point 3."
  ],
  "riskMatrix": {
    "Liability & Indemnity": { "level": "High/Med/Low", "summary": "Caps, Knock-for-knock, Carve-outs." },
    "HSE & Operational": { "level": "High/Med/Low", "summary": "Safety criticals, Stop Work, Pollution." },
    "Termination & Exit": { "level": "High/Med/Low", "summary": "Convenience rights, fees, notice periods." },
    "Compliance & Governance": { "level": "High/Med/Low", "summary": "Sanctions check (Google), Local Content, ABC." }
  },
  "scope": {
    "pricingModel": "Lumpsum / Unit Rate / Reimbursable",
    "paymentTerms": "e.g. Net 45 Days",
    "deliverables": "Key goods or services to be provided."
  },
  "detailedAnalysis": "Markdown string containing the full deep-dive report (Commercials, Scope, Legal, HSE, Recommendations) formatted with ## Headings and bullets."
}
"""

# ==========================================
# 📄 PDF REPORT ENGINE (Updated for Markdown)
# ==========================================
class StrategicReport(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 10, 'CONFIDENTIAL // STRATEGIC CONTRACT ASSESSMENT', 0, 1, 'C')
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
        # Basic markdown cleaning
        lines = body.split('\n')
        for line in lines:
            if line.startswith('## '):
                self.ln(4)
                self.set_font('Arial', 'B', 12)
                self.set_text_color(0, 0, 0)
                self.cell(0, 8, line.replace('## ', ''), 0, 1)
            elif line.startswith('- ') or line.startswith('* '):
                self.set_font('Arial', '', 11)
                self.set_text_color(50, 50, 50)
                self.set_x(15) # Indent bullets
                self.multi_cell(0, 6, chr(149) + " " + line[2:]) # Bullet char
            else:
                self.set_font('Arial', '', 11)
                self.set_text_color(50, 50, 50)
                self.multi_cell(0, 6, line)
        self.ln(2)

def generate_pdf(data):
    pdf = StrategicReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # 1. Title Page Info
    details = data.get('contractDetails', {})
    risk = data.get('overallRisk', {})
    
    pdf.set_font('Arial', 'B', 24)
    pdf.multi_cell(0, 10, "Strategic Contract Assessment", 0, 'C')
    pdf.ln(5)
    
    pdf.set_font('Arial', 'B', 14)
    pdf.multi_cell(0, 8, str(details.get('title', 'Contract Analysis')), 0, 'C')
    pdf.ln(10)

    # 2. Executive Synthesis Box
    pdf.set_fill_color(240, 240, 240)
    pdf.rect(10, pdf.get_y(), 190, 50, 'F')
    pdf.set_xy(15, pdf.get_y() + 5)
    
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, f"VERDICT: {risk.get('level', 'N/A').upper()} RISK ({risk.get('score', 0)}/100)", 0, 1)
    
    pdf.set_font('Arial', '', 11)
    exec_sum = data.get('executiveSummary', [])
    for item in exec_sum:
        pdf.set_x(15)
        pdf.multi_cell(180, 6, item)
    pdf.ln(10)

    # 3. Detailed Analysis (The McKinsey Report)
    report_body = data.get('detailedAnalysis', "No detailed analysis generated.")
    pdf.chapter_body(report_body)

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
        # 1.5 Pro has large context, reading up to 120 pages safely
        for i in range(min(len(reader.pages), 120)): 
            text += reader.pages[i].extract_text() + "\n"
        return text
    except: return None

# ==========================================
# 🧠 ANALYSIS ENGINE (The "Senior Strategist")
# ==========================================
def run_analysis(text):
    genai.configure(api_key=API_KEY)
    
    # Enable Google Search Tool for Background Checks
    tools = [
        {"google_search_retrieval": {
            "dynamic_retrieval_config": {
                "mode": "dynamic",
                "dynamic_threshold": 0.3,
            }
        }}
    ]
    
    # Configure Model with Tools
    model = genai.GenerativeModel(ACTIVE_MODEL, tools=tools)
    
    # The McKinsey-Style Prompt
    base_instruction = """
    YOU ARE A SENIOR LEGAL STRATEGIST AND PROCUREMENT MANAGER.
    
    Your task is to analyze the provided contract and extract structured data for a management dashboard, as well as a detailed written report.

    **STYLE GUIDE (McKinsey Style):**
    - **Synthesis over Summary**: Do not just repeat clauses; explain "So What?" and the business impact.
    - **Active Voice**: Use direct, punchy sentences.
    - **Strict Bullet Points**: All lists must be formatted as clean, separate bullet points.
    - **Data-Driven**: Where possible, extract numbers, caps, and dates explicitly.

    **CRITICAL INSTRUCTION**: You MUST perform a background check on the Counterparty. 
    Look for:
    1. Recent financial news (bankruptcy, stock drops, liquidity issues).
    2. Sanctions lists (OFAC, EU, UN) or trade restrictions.
    3. Adverse media (lawsuits, corruption allegations, major operational failures).
    Fill the 'Compliance & Governance' section of the riskMatrix based on these search results.

    You must return a JSON object matching the provided schema.

    1. **Structured Data Fields**:
       - **contractDetails**: Identify the official title and parties.
       - **overallRisk**: Assess as 'High', 'Medium', or 'Low' based on liability and commercial risk.
       - **keyCommercials**: Extract value, duration, and contract type.
       - **executiveSummary**: Provide 3-5 concise, high-impact bullet points using Markdown format (hyphen start). Focus on "Bottom Line Up Front" (BLUF).
       - **riskMatrix**: Specific array of risk items (Liability, HSE, Termination, Compliance).
       - **scope**: Extract pricing model, payment terms, deliverables.

    2. **detailedAnalysis Field**:
       - This field should contain the detailed "Deep Dive" analysis in Markdown format.
       - Use **McKinsey-style headings** (## Heading Name).
       - Structure:
         - ## Commercial & Financial Profile
         - ## Scope of Work & Technical Review
         - ## Liquidated Damages and Service Credits
         - ## Liability, Indemnities, Insurance
         - ## HSE, Operational and Performance Risk
         - ## Term, Termination, Breach and Force Majeure
         - ## Legal, Compliance and Governance (Include Background Check Findings Here)
         - ## Strategic Recommendations
       - Ensure every bullet point is separated by a newline.
    
    OUTPUT SCHEMA:
    """ + SCHEMA_DEF + """
    
    CONTRACT TEXT:
    """ + text[:150000]
    
    try:
        response = model.generate_content(base_instruction, generation_config={"response_mime_type": "application/json"})
        return json.loads(response.text)
    except Exception as e:
        return {"error": str(e)}

# ==========================================
# 🖥️ UI / DASHBOARD
# ==========================================
def main():
    
    # --- UI STYLING ---
    st.markdown("""
        <style>
        .stApp { background-color: #ffffff; font-family: 'Helvetica Neue', sans-serif; }
        .metric-card {
            background-color: white; border: 1px solid #e5e7eb; border-radius: 8px;
            padding: 20px; box-shadow: 0 1px 2px 0 rgba(0,0,0,0.05);
            height: 100%; display: flex; flex-direction: column;
        }
        .card-label { font-size: 0.75rem; color: #6b7280; text-transform: uppercase; font-weight: 700; margin-bottom: 5px; }
        .card-value { font-size: 1.25rem; font-weight: 700; color: #111827; }
        .risk-badge { padding: 4px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; display: inline-block; }
        .bg-high { background-color: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }
        .bg-med { background-color: #fffbeb; color: #92400e; border: 1px solid #fde68a; }
        .bg-low { background-color: #ecfdf5; color: #065f46; border: 1px solid #a7f3d0; }
        </style>
    """, unsafe_allow_html=True)

    # --- SIDEBAR ---
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
        uploaded_file = st.file_uploader("Upload Agreement (PDF)", type=["pdf"])
        
        if st.button("Logout"):
            st.session_state.authenticated = False
            st.rerun()

    # --- MAIN CONTENT ---
    c1, c2 = st.columns([3,1])
    with c1:
        st.markdown('### ⚙️ CONTRACT INTELLIGENCE', unsafe_allow_html=True)
        st.caption("Strategic Analysis & Procurement Guardrails (v5.0)")
    
    if uploaded_file:
        if st.button("🚀 Run Strategic Analysis"):
            with st.spinner("⚙️ Reading Contract, Checking Sanctions, Generating Strategy..."):
                text = extract_text(uploaded_file)
                if text:
                    result = run_analysis(text)
                    if "error" not in result:
                        st.session_state.result = result
                        st.rerun()
                    else: st.error(f"Analysis Failed: {result['error']}")

    # --- DASHBOARD RENDER ---
    if "result" in st.session_state:
        data = st.session_state.result
        
        # 1. METADATA & RISK SCORE
        details = data.get('contractDetails', {})
        risk = data.get('overallRisk', {})
        comm = data.get('keyCommercials', {})
        
        st.markdown(f"## {details.get('title', 'Contract Assessment')} ✅")
        st.caption(f"Parties: {', '.join(details.get('parties', []))}")
        
        # Metric Row
        c1, c2, c3, c4 = st.columns(4)
        
        # Risk Logic
        lvl = risk.get('level', 'Medium')
        bg_cls = "bg-high" if lvl == 'High' else "bg-med" if lvl == 'Medium' else "bg-low"
        
        with c1:
            st.markdown(f"""
            <div class="metric-card">
                <div class="card-label">Overall Risk</div>
                <div><span class="risk-badge {bg_cls}">{lvl}</span> <span style="font-size:1.2rem; font-weight:700;">{risk.get('score')}/100</span></div>
                <div style="font-size:0.8rem; color:#666; margin-top:5px;">{risk.get('rationale')}</div>
            </div>
            """, unsafe_allow_html=True)
            
        with c2: st.markdown(f'<div class="metric-card"><div class="card-label">Contract Value</div><div class="card-value">{comm.get("value")}</div></div>', unsafe_allow_html=True)
        with c3: st.markdown(f'<div class="metric-card"><div class="card-label">Duration</div><div class="card-value" style="font-size:1rem;">{comm.get("duration")}</div></div>', unsafe_allow_html=True)
        with c4: st.markdown(f'<div class="metric-card"><div class="card-label">Type</div><div class="card-value">{comm.get("contractType")}</div></div>', unsafe_allow_html=True)

        st.markdown("---")

        # 2. EXECUTIVE SUMMARY (BLUF)
        st.subheader("📝 Executive Synthesis (BLUF)")
        for item in data.get('executiveSummary', []):
            st.markdown(item)
            
        st.markdown("---")

        # 3. RISK MATRIX GRID
        st.subheader("🛡️ Risk & Compliance Matrix")
        r_grid = data.get('riskMatrix', {})
        
        rc1, rc2 = st.columns(2)
        
        def render_risk_box(title, obj):
            l = obj.get('level', 'Low')
            b = "bg-high" if l == 'High' else "bg-med" if l == 'Medium' else "bg-low"
            return f"""
            <div class="metric-card" style="margin-bottom:20px;">
                <div style="display:flex; justify-content:space-between;">
                    <span style="font-weight:700;">{title}</span>
                    <span class="risk-badge {b}">{l}</span>
                </div>
                <p style="font-size:0.9rem; margin-top:10px;">{obj.get('summary')}</p>
            </div>
            """

        with rc1:
            st.markdown(render_risk_box("Liability & Indemnity", r_grid.get('Liability & Indemnity', {})), unsafe_allow_html=True)
            st.markdown(render_risk_box("HSE & Operational", r_grid.get('HSE & Operational', {})), unsafe_allow_html=True)
            
        with rc2:
            st.markdown(render_risk_box("Termination & Exit", r_grid.get('Termination & Exit', {})), unsafe_allow_html=True)
            st.markdown(render_risk_box("Compliance & Sanctions Check", r_grid.get('Compliance & Governance', {})), unsafe_allow_html=True)

        # 4. DEEP DIVE REPORT
        st.markdown("### 📋 Detailed Strategic Report")
        with st.expander("View Full McKinsey-Style Analysis", expanded=True):
            st.markdown(data.get('detailedAnalysis', 'Report generation failed.'))

        # 5. PDF EXPORT
        st.markdown("---")
        if st.button("📄 Download Strategic Report (PDF)"):
            pdf_bytes = generate_pdf(data)
            st.download_button("📥 Click to Download", pdf_bytes, "Strategic_Report.pdf", "application/pdf")

if __name__ == "__main__":
    main()
