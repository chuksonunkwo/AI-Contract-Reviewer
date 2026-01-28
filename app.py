import streamlit as st
import google.generativeai as genai
import json
import os
import requests
import tempfile
import time
from fpdf import FPDF
import re
from google.api_core import exceptions

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
st.set_page_config(
    page_title="Strategic Contract Assessment", 
    layout="wide", 
    page_icon="🛡️",
    initial_sidebar_state="expanded"
)

# ⚡ CORE ENGINE
ACTIVE_MODEL = "gemini-2.0-flash-exp"
APP_VERSION = "6.1.0 (Schema Stable)"

# 1. API KEY
try:
    API_KEY = os.environ.get("GEMINI_API_KEY")
    if not API_KEY:
        API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    API_KEY = "MISSING_KEY"

# 2. WEBHOOK
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL")
GUMROAD_PRODUCT_ID = "xGeemEFxpMJUbG-jUVxIHg==" 

# ==========================================
# 🧱 THE SCHEMA (DEFINED AS TEXT FOR PROMPT)
# ==========================================
# We inject this directly into the prompt to guarantee structure 
# without relying on SDK-specific schema parameters that might fail.

SCHEMA_DEF = """
{
  "contract_details": {
    "title": "string",
    "parties": ["string"]
  },
  "risk_score": {
    "score": 0-100,
    "level": "High/Medium/Low",
    "rationale": "string"
  },
  "executive_summary": "Markdown bullet points",
  "commercials": {
    "value_description": "Extracted Rate/Value",
    "duration": "string",
    "termination_fee": "string"
  },
  "legal_risks": [
    { "area": "Indemnity/Liability", "risk_level": "High/Med/Low", "finding": "string" }
  ],
  "hse_risks": [
    { "area": "Stop Work/Safety Case", "risk_level": "High/Med/Low", "finding": "string" }
  ],
  "compliance": {
    "local_content": "string",
    "sanctions": "string"
  },
  "operational_scope": {
    "scope_summary": "string",
    "key_equipment": "string"
  },
  "deep_dive_report": "Full Markdown report"
}
"""

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
            "content": f"🚨 **Run:** `{filename}` ({round(file_size/1024/1024,1)}MB) | User: `{license_key[-4:]}`"
        })
    except: pass

def repair_json(json_str):
    json_str = re.sub(r"```json", "", json_str)
    json_str = re.sub(r"```", "", json_str)
    json_str = json_str.strip()
    return json_str

def extract_json(text):
    try:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        json_str = match.group(0) if match else text
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
    if len(value) > 35: return "See Report" 
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
    title = safe_get(data, ['contract_details', 'title'], 'Contract Analysis')
    pdf.multi_cell(0, 8, str(title).encode('latin-1', 'replace').decode('latin-1'), 0, 'L')
    pdf.ln(5)
    
    # Exec Summary
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "1. EXECUTIVE SYNTHESIS", 0, 1, 'L', fill=True)
    pdf.ln(3)
    pdf.set_font("Helvetica", "", 10)
    summary = safe_get(data, ['executive_summary'], 'No summary available.')
    pdf.multi_cell(0, 6, str(summary).encode('latin-1', 'replace').decode('latin-1'))
    pdf.ln(5)

    # Commercials
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "2. COMMERCIAL TERMS", 0, 1, 'L', fill=True)
    pdf.ln(3)
    pdf.set_font("Helvetica", "", 10)
    comm = safe_get(data, ['commercials'], {})
    if isinstance(comm, dict):
        for k, v in comm.items():
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(50, 6, f"{k.capitalize().replace('_', ' ')}:", 0, 0)
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, 6, str(v).encode('latin-1', 'replace').decode('latin-1'))
            pdf.ln(1)
    pdf.ln(5)

    # Legal Risks
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "3. LEGAL RISK VECTORS", 0, 1, 'L', fill=True)
    pdf.ln(3)
    risks = safe_get(data, ['legal_risks'], [])
    for item in risks:
        pdf.set_font("Helvetica", "B", 10)
        area = str(item.get('area', 'Risk')).encode('latin-1', 'replace').decode('latin-1')
        risk_level = str(item.get('risk_level', '-')).encode('latin-1', 'replace').decode('latin-1')
        pdf.cell(0, 6, f"{area} ({risk_level})", 0, 1)
        pdf.set_font("Helvetica", "", 10)
        finding = str(item.get('finding', '')).encode('latin-1', 'replace').decode('latin-1')
        pdf.multi_cell(0, 6, finding)
        pdf.ln(3)
    pdf.ln(5)

    # HSE Risks
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "4. HSE & SAFETY VECTORS", 0, 1, 'L', fill=True)
    pdf.ln(3)
    hse = safe_get(data, ['hse_risks'], [])
    for item in hse:
        pdf.set_font("Helvetica", "B", 10)
        area = str(item.get('area', 'HSE')).encode('latin-1', 'replace').decode('latin-1')
        risk_level = str(item.get('risk_level', '-')).encode('latin-1', 'replace').decode('latin-1')
        pdf.cell(0, 6, f"{area} ({risk_level})", 0, 1)
        pdf.set_font("Helvetica", "", 10)
        finding = str(item.get('finding', '')).encode('latin-1', 'replace').decode('latin-1')
        pdf.multi_cell(0, 6, finding)
        pdf.ln(3)

    return pdf.output(dest='S').encode('latin-1', 'replace')

# ==========================================
# 🧠 CLOUD ENGINE (ROBUST PROMPT MODE)
# ==========================================

MASTER_PROMPT = f"""
ACT AS A FORENSIC CONTRACT AUDITOR.
Review this ENTIRE contract (including Appendices).

You MUST output your analysis in this STRICT JSON FORMAT:
{SCHEMA_DEF}

CRITICAL EXTRACTION INSTRUCTIONS:

1. **commercials**:
   - `value_description`: Extract the Base Operating Rate (e.g. "$180k/day"). Look in the Pricing Appendix.
   - `termination_fee`: Extract the calculation formula.

2. **legal_risks** (STRICTLY CONTRACTUAL):
   - Include: Indemnities (Knock-for-knock status), Liability Caps (Exact $ amount), Consequential Loss Waivers.
   - Do NOT put Safety items here.

3. **hse_risks** (STRICTLY OPERATIONAL/SAFETY):
   - Include: Stop Work Authority, Safety Case requirements, Environmental Liability, PPE.

4. **compliance**:
   - `local_content`: Look for "Namibian/Local Content" quotas.

5. **deep_dive_report**:
   - Create a detailed Markdown report with headers.

Ensure valid JSON output. No preamble.
"""

def generate_with_retry(model, prompt, file_obj):
    max_retries = 3
    base_delay = 5

    for attempt in range(max_retries):
        try:
            return model.generate_content(
                [prompt, file_obj],
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.0
                }
            )
        except exceptions.ResourceExhausted:
            if attempt < max_retries - 1:
                wait_time = base_delay * (2 ** attempt)
                st.toast(f"⚠️ API Busy. Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise 
        except Exception as e:
            raise e 

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
                
        with st.spinner("🧠 Forensic Scan (Schema Mode)..."):
            model = genai.GenerativeModel(ACTIVE_MODEL)
            response = generate_with_retry(model, MASTER_PROMPT, g_file)
            
        os.remove(tmp_path)
        
        try:
            return json.loads(response.text), None
        except:
            return None, "Failed to parse JSON response."
        
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
            
            data_dict, error = process_file_cloud(uploaded_file, st.session_state.license_key)
            
            if data_dict:
                st.session_state.analysis = data_dict
                st.rerun()
            else: 
                st.error(f"Processing Failed: {error}")

    if "analysis" in st.session_state:
        data = st.session_state.analysis
        
        # HERO METRICS
        c1, c2, c3, c4 = st.columns(4)
        score = safe_get(data, ['risk_score', 'score'], 0)
        level = safe_get(data, ['risk_score', 'level'], 'Unknown')
        
        comm_val = format_currency(safe_get(data, ['commercials', 'value_description'], "N/A"))
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
        t1, t2, t3, t4, t5, t6 = st.tabs(["📄 Briefing", "💰 Commercials", "⚖️ Legal", "⛑️ HSE", "⚙️ Ops", "🚩 Compliance"])
        
        with t1:
            st.subheader("Executive Synthesis")
            st.markdown(safe_get(data, ['executive_summary']))
            st.divider()
            pdf_bytes = create_pdf(data)
            st.download_button("📥 Download Enterprise Report (PDF)", pdf_bytes, "Assessment.pdf", "application/pdf")

        with t2:
            st.subheader("Commercial Terms")
            comm_data = safe_get(data, ['commercials'], {})
            if isinstance(comm_data, dict):
                for k, v in comm_data.items():
                    st.markdown(f"**{k.capitalize().replace('_', ' ')}:** {v}")
            else:
                st.markdown(comm_data)

        with t3:
            st.subheader("Legal Risk Vectors (Contractual)")
            risks = safe_get(data, ['legal_risks'], [])
            if risks: st.dataframe(pd.DataFrame(risks), use_container_width=True, hide_index=True)
            else: st.info("No significant legal risks detected.")

        with t4:
            st.subheader("HSE & Safety Vectors")
            hse = safe_get(data, ['hse_risks'], [])
            if hse: st.dataframe(pd.DataFrame(hse), use_container_width=True, hide_index=True)
            else: st.info("No specific HSE flags detected.")

        with t5:
            st.subheader("Operational & Technical Specs")
            ops_scope = safe_get(data, ['operational_scope'], {})
            if ops_scope:
                st.write("**Scope Summary:**", ops_scope.get('scope_summary', 'N/A'))
                st.write("**Key Equipment:**", ops_scope.get('key_equipment', 'N/A'))
            else: st.info("No critical operational constraints found.")

        with t6:
            st.subheader("Compliance & Regulatory")
            comp = safe_get(data, ['compliance'], {})
            if isinstance(comp, dict):
                for k, v in comp.items():
                    st.markdown(f"**{k.capitalize().replace('_', ' ')}:** {v}")
            else: st.markdown(comp)

if __name__ == "__main__":
    main()
