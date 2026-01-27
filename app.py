import streamlit as st
import google.generativeai as genai
import json
import pandas as pd
import os
import requests
import ast
import tempfile
import time
from fpdf import FPDF
import re

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
st.set_page_config(
    page_title="Strategic Contract Assessment", 
    layout="wide", 
    page_icon="🛡️",
    initial_sidebar_state="expanded"
)

# ⚡ CORE ENGINE: Switched to Production Stable to fix 429 Errors
ACTIVE_MODEL = "gemini-1.5-flash"
APP_VERSION = "4.3.0 (Production Stable)"

# 1. API KEY
try:
    API_KEY = os.environ.get("GEMINI_API_KEY")
    if not API_KEY:
        API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    API_KEY = "MISSING_KEY"

# 2. WEBHOOK & GUMROAD
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL")
GUMROAD_PRODUCT_ID = "xGeemEFxpMJUbG-jUVxIHg==" 

# ==========================================
# 🛠️ UTILITIES
# ==========================================

def check_gumroad_license(key):
    url = "https://api.gumroad.com/v2/licenses/verify"
    params = {"product_id": GUMROAD_PRODUCT_ID, "license_key": key, "increment_uses_count": "false"}
    try:
        response = requests.post(url, data=params)
        data = response.json()
        if not data.get("success"): return False, "❌ Invalid Key"
        if data.get("purchase", {}).get("refunded"): return False, "⛔ Refunded"
        return True, "✅ Active"
    except: return False, "Connection Error"

def log_usage(license_key, filename, file_size):
    if not DISCORD_WEBHOOK: return
    try:
        requests.post(DISCORD_WEBHOOK, json={
            "content": f"🚨 **Cloud Run:** `{filename}` ({round(file_size/1024/1024,1)}MB) | User: `{license_key[-4:]}`"
        })
    except: pass

def repair_json(json_str):
    # Remove markdown code blocks
    json_str = re.sub(r"```json", "", json_str)
    json_str = re.sub(r"```", "", json_str)
    json_str = json_str.strip()
    
    # Attempt to fix truncated JSON
    open_braces = json_str.count('{')
    close_braces = json_str.count('}')
    open_brackets = json_str.count('[')
    close_brackets = json_str.count(']')
    
    json_str += ']' * (open_brackets - close_brackets)
    json_str += '}' * (open_braces - close_braces)
    
    return json_str

def extract_json(text):
    try:
        # First, try to find the JSON block
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            json_str = match.group(0)
        else:
            json_str = text

        return json.loads(json_str)
    except json.JSONDecodeError:
        try:
            return json.loads(repair_json(json_str))
        except:
            return None

def safe_get(data, path, default="N/A"):
    try:
        for key in path:
            if isinstance(data, list): data = data[0] if data else default
            elif isinstance(data, dict): data = data.get(key, default)
            else: return default
        return data
    except: return default

def format_currency(value):
    if not isinstance(value, str): return str(value)
    if len(value) > 25: return "See Report" 
    return value

# ==========================================
# 📄 PDF REPORT GENERATOR
# ==========================================
class StrategicReport(FPDF):
    def header(self):
        self.set_font('Helvetica', 'B', 10)
        self.set_text_color(80, 80, 80)
        self.cell(0, 10, f'CONFIDENTIAL // STRATEGIC ASSESSMENT // v{APP_VERSION}', 0, 1, 'L')
        self.line(10, 20, 200, 20)
        self.ln(10)
    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

def create_pdf(data):
    pdf = StrategicReport()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # Title
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(0, 0, 0)
    title = safe_get(data, ['contractDetails', 'title'], 'Contract Analysis')
    pdf.multi_cell(0, 8, str(title).encode('latin-1', 'replace').decode('latin-1'), 0, 'L')
    pdf.ln(5)
    
    # Exec Summary
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "1. EXECUTIVE SYNTHESIS", 0, 1, 'L', fill=True)
    pdf.ln(3)
    pdf.set_font("Helvetica", "", 10)
    summary = safe_get(data, ['executiveSummary'], 'No summary available.')
    pdf.multi_cell(0, 6, str(summary).encode('latin-1', 'replace').decode('latin-1'))
    pdf.ln(5)

    # Risk Table
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "2. KEY RISK VECTORS", 0, 1, 'L', fill=True)
    pdf.ln(3)
    risks = safe_get(data, ['riskTable'], [])
    for item in risks:
        pdf.set_font("Helvetica", "B", 10)
        area = str(item.get('area', 'Risk')).encode('latin-1', 'replace').decode('latin-1')
        risk_level = str(item.get('risk', '-')).encode('latin-1', 'replace').decode('latin-1')
        pdf.cell(0, 6, f"{area} ({risk_level})", 0, 1)
        pdf.set_font("Helvetica", "", 10)
        finding = str(item.get('finding', '')).encode('latin-1', 'replace').decode('latin-1')
        pdf.multi_cell(0, 6, finding)
        pdf.ln(3)

    return pdf.output(dest='S').encode('latin-1', 'replace')

# ==========================================
# 🧠 CLOUD ENGINE (ENHANCED PROMPTS)
# ==========================================

MASTER_PROMPT = """
You are a Senior Legal Counsel & Commercial Analyst in the Oil & Gas sector.
I have uploaded a complex drilling/service contract.
Scan the ENTIRE document from Page 1 to the final Appendix.

Your Goal: Provide a "Board-Level" Strategic Risk Assessment.

CRITICAL EXTRACTION RULES:
1. COMMERCIALS: Search the Appendices for the "Schedule of Rates" or "Compensation".
   - Extract the specific Base Day Rate (e.g. $250,000/day).
   - Extract Mobilization/Demobilization Fees.
   - Extract Early Termination Fees (e.g. "50% of day rate").
   *If exact numbers are redacted, state "Redacted/TBD" but describe the mechanism.*

2. LEGAL RISKS (The "Killer Clauses"):
   - INDEMNITY: Is it "Knock-for-Knock"? (Good). Or is the Contractor liable for Company negligence? (Bad).
   - LIABILITY CAP: What is the cap? (e.g. "100% of Contract Price" or "$5M").
   - CONSEQUENTIAL LOSS: Is there a mutual waiver? (Standard). Or is it missing? (High Risk).

3. COMPLIANCE & HSE:
   - HSE: Are there specific "Stop Work Authority" or "Zero Tolerance" clauses?
   - LOCAL CONTENT: (Crucial for Africa/Namibia). What are the hiring quotas or local spend requirements?
   - SANCTIONS: Are there strict US/EU sanctions warranties?

4. OPERATIONAL SCOPE:
   - What vessel/rig is named? (e.g. "Deepwater Titan").
   - What is the firm duration vs option periods?

OUTPUT FORMAT:
Return strictly valid JSON. Do not write markdown text outside the JSON.

{
  "contractDetails": { "title": "string", "parties": ["string"] },
  "riskScore": { "score": 0-100, "level": "High/Medium/Low", "rationale": "One sentence explaining the score" },
  "executiveSummary": "A dense, high-value summary of the deal structure, primary risks, and strategic value. Use bullet points.",
  "commercials": { 
      "value": "The Day Rate or Total Value (e.g. $370k/day)", 
      "duration": "Firm Term + Options (e.g. 2 Wells + 1 Option)",
      "terminationFee": "Specific formula (e.g. 70% of Rate)"
  },
  "compliance": {
      "entity": "Contractor Name",
      "sanctions": { "status": "Clean/Flagged", "details": "Summary of sanctions clause" },
      "localContent": "Details of local hiring/purchasing obligations"
  },
  "riskTable": [
      { "area": "Indemnity Regime", "risk": "High/Med/Low", "finding": "Detail the knock-for-knock status and any carve-outs." },
      { "area": "Liability Cap", "risk": "High/Med/Low", "finding": "Specific cap amount and exclusions (e.g. Gross Negligence)." },
      { "area": "HSE & Safety", "risk": "High/Med/Low", "finding": "Safety protocols, Stop Work Authority, and environmental liability." }
  ],
  "operationalTable": [
      { "area": "Scope of Work", "finding": "Details of the drilling campaign or service." },
      { "area": "Key Equipment", "finding": "Primary vessel/rig or equipment specs." }
  ],
  "deepDive": "A comprehensive markdown report structured with headers (##). Include a section specifically analyzing the 'Hidden Risks' in the appendices."
}
"""

def process_file_cloud(uploaded_file, license_key):
    if not API_KEY or API_KEY == "MISSING_KEY": return None, "API Key Missing"
    
    log_usage(license_key, uploaded_file.name, uploaded_file.size)
    genai.configure(api_key=API_KEY)
    
    try:
        suffix = ".pdf" if uploaded_file.type == "application/pdf" else ".docx"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            tmp_path = tmp_file.name
            
        with st.spinner("☁️ Uploading to Neural Engine..."):
            g_file = genai.upload_file(tmp_path, mime_type=uploaded_file.type)
            
            while g_file.state.name == "PROCESSING":
                time.sleep(2)
                g_file = genai.get_file(g_file.name)
                
        with st.spinner("🧠 Analyzing Contract (This may take 45s)..."):
            model = genai.GenerativeModel(ACTIVE_MODEL)
            response = model.generate_content(
                [MASTER_PROMPT, g_file],
                generation_config={"response_mime_type": "application/json"}
            )
            
        os.remove(tmp_path)
        return response.text, None
        
    except Exception as e:
        return None, str(e)

# ==========================================
# 🖥️ UI (ENTERPRISE DASHBOARD)
# ==========================================
def main():
    
    st.markdown("""
        <style>
        .stApp { background-color: #f8fafc; font-family: 'Inter', sans-serif; }
        .metric-card { background-color: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); text-align: center; }
        .metric-label { color: #64748b; font-size: 0.8rem; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; }
        .metric-value { color: #0f172a; font-size: 1.6rem; font-weight: 700; margin-top: 5px; }
        </style>
    """, unsafe_allow_html=True)

    if 'license_verified' not in st.session_state: st.session_state.license_verified = False
    if 'license_key' not in st.session_state: st.session_state.license_key = ""

    with st.sidebar:
        st.title("🛡️ Secure Portal")
        st.caption(f"System: {APP_VERSION}")
        st.success("🟢 Cloud Link Active")
        st.markdown("---")

        if not st.session_state.license_verified:
            st.warning("🔒 Authorization Required")
            entered_key = st.text_input("License Key", type="password")
            if st.button("Authenticate"):
                valid, msg = check_gumroad_license(entered_key)
                if valid:
                    st.session_state.license_verified = True
                    st.session_state.license_key = entered_key
                    st.success(msg)
                    st.rerun()
                else: st.error(msg)
            st.stop()
        else:
            if st.button("End Session"):
                st.session_state.license_verified = False
                st.rerun()
            st.markdown("---")

        uploaded_file = st.file_uploader("Upload Agreement", type=["pdf", "docx", "txt"])

    st.markdown("## Strategic Contract Assessment")
    st.markdown("##### ⚡ Oil & Gas Specialist Edition")
    st.markdown("---")

    if uploaded_file:
        if st.button("Initialize Enterprise Analysis"):
            
            raw_response, error = process_file_cloud(uploaded_file, st.session_state.license_key)
            
            if raw_response:
                data_dict = extract_json(raw_response)
                if data_dict:
                    st.session_state.analysis = data_dict
                    st.rerun()
                else:
                    st.warning("⚠️ Structure Parse Warning: Switching to Raw View")
                    st.session_state.analysis = {"riskScore": {"score": 0}, "executiveSummary": raw_response}
                    st.rerun()
            else: st.error(f"Processing Failed: {error}")

    if "analysis" in st.session_state:
        data = st.session_state.analysis
        
        # HERO METRICS
        c1, c2, c3, c4 = st.columns(4)
        score = safe_get(data, ['riskScore', 'score'], 0)
        level = safe_get(data, ['riskScore', 'level'], 'Unknown')
        
        comm_val = format_currency(safe_get(data, ['commercials', 'value'], "N/A"))
        comm_dur = format_currency(safe_get(data, ['commercials', 'duration'], "N/A"))
        
        color = "#10b981" # Green
        if int(score) > 75: color = "#ef4444" # Red
        elif int(score) > 40: color = "#f59e0b" # Orange
        
        with c1: st.markdown(f"<div class='metric-card'><div class='metric-label'>Risk Score</div><div class='metric-value' style='color: {color};'>{score}/100</div><small>{level}</small></div>", unsafe_allow_html=True)
        with c2: st.markdown(f"<div class='metric-card'><div class='metric-label'>Value / Rate</div><div class='metric-value' style='font-size: 1.4rem;'>{comm_val}</div></div>", unsafe_allow_html=True)
        with c3: st.markdown(f"<div class='metric-card'><div class='metric-label'>Duration</div><div class='metric-value' style='font-size: 1.4rem;'>{comm_dur}</div></div>", unsafe_allow_html=True)
        with c4: st.markdown(f"<div class='metric-card'><div class='metric-label'>Action</div><div class='metric-value' style='font-size: 1.4rem;'>{'⚠️ Review' if int(score) > 40 else '✅ Approved'}</div></div>", unsafe_allow_html=True)

        st.markdown("---")
        
        # TABS
        t1, t2, t3, t4, t5 = st.tabs(["📄 Briefing", "💰 Commercials", "⚖️ Legal & HSE", "⚙️ Ops", "🚩 Compliance"])
        
        with t1:
            st.subheader("Executive Synthesis")
            st.markdown(safe_get(data, ['executiveSummary']))
            st.divider()
            pdf_bytes = create_pdf(data)
            st.download_button("📥 Download Enterprise Report (PDF)", pdf_bytes, "Assessment.pdf", "application/pdf")

        with t2:
            st.subheader("Commercial Terms")
            comm_data = safe_get(data, ['commercials'], {})
            if isinstance(comm_data, dict):
                for k, v in comm_data.items():
                    st.markdown(f"**{k.capitalize()}:** {v}")
            else:
                st.markdown(comm_data)

        with t3:
            st.subheader("Legal & HSE Risks")
            risks = safe_get(data, ['riskTable'], [])
            if risks: st.dataframe(pd.DataFrame(risks), use_container_width=True, hide_index=True)
            else: st.info("No significant risks detected.")

        with t4:
            st.subheader("Operational & Technical Specs")
            ops = safe_get(data, ['operationalTable'], [])
            if ops: st.dataframe(pd.DataFrame(ops), use_container_width=True, hide_index=True)
            else: st.info("No critical operational constraints found.")

        with t5:
            st.subheader("Compliance & Regulatory")
            comp = safe_get(data, ['compliance'], {})
            if isinstance(comp, dict):
                for k, v in comp.items():
                    if isinstance(v, dict): st.write(f"**{k}:**", v) 
                    else: st.markdown(f"**{k.capitalize()}:** {v}")
            else: st.markdown(comp)

if __name__ == "__main__":
    main()
