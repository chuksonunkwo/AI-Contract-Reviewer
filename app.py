import streamlit as st
import os
import time
import json

# ==========================================
# 🔧 SYSTEM DIAGNOSTICS (PRE-FLIGHT CHECK)
# ==========================================
# We check imports BEFORE the app starts to prevent "White Screen of Death"
try:
    import google.generativeai as genai
    from fpdf import FPDF
    import PyPDF2
    import requests
    from google.api_core import exceptions
    import io
    IMPORTS_OK = True
except ImportError as e:
    st.error(f"❌ CRITICAL SYSTEM ERROR: Missing Library. {e}")
    st.info("Please update your 'requirements.txt' file to include: PyPDF2, fpdf, google-generativeai")
    st.stop()

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
st.set_page_config(
    page_title="AI Contract Reviewer", 
    layout="wide", 
    page_icon="⚖️",
    initial_sidebar_state="expanded"
)

APP_NAME = "AI Contract Reviewer"
APP_VERSION = "1.0 (Stable Enterprise)"
ACTIVE_MODEL = "gemini-2.0-flash-exp"

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
# 🧱 THE SCHEMA
# ==========================================
SCHEMA_DEF = """
{
  "contract_details": {
    "title": "string",
    "parties": ["string"],
    "governing_law": "string"
  },
  "risk_score": {
    "score": 0-100,
    "level": "High/Medium/Low",
    "rationale": "string"
  },
  "executive_summary": "Markdown bullet points.",
  "commercials": {
    "value_description": "Extracted Rate/Value",
    "duration": "string",
    "termination_fee": "string",
    "payment_terms": "string"
  },
  "legal_risks": [
    { "area": "Indemnity/Liability", "risk_level": "High/Med/Low", "finding": "Summary", "source_text": "Quote" }
  ],
  "hse_risks": [
    { "area": "Safety/Environment", "risk_level": "High/Med/Low", "finding": "Summary", "source_text": "Quote" }
  ],
  "compliance": { "local_content": "string", "sanctions": "string" },
  "operational_scope": { "scope_summary": "string", "key_equipment": "string" }
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
        return True, "✅ Access Granted"
    except: return False, "Connection Error"

def log_usage(license_key, filename, file_size):
    if not DISCORD_WEBHOOK: return
    try:
        requests.post(DISCORD_WEBHOOK, json={
            "content": f"🚨 **Run:** `{filename}` ({round(file_size/1024/1024,1)}MB) | User: `{license_key[-4:]}`"
        })
    except: pass

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
# 📄 PDF GENERATOR
# ==========================================
class StrategicReport(FPDF):
    def header(self):
        self.set_font('Helvetica', 'B', 10)
        self.set_text_color(80, 80, 80)
        self.cell(0, 10, f'CONFIDENTIAL // {APP_NAME} // v{APP_VERSION}', 0, 1, 'L')
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
    
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(0, 0, 0)
    title = safe_get(data, ['contract_details', 'title'], 'Contract Analysis')
    pdf.multi_cell(0, 8, str(title).encode('latin-1', 'replace').decode('latin-1'), 0, 'L')
    pdf.ln(5)
    
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "1. EXECUTIVE SYNTHESIS", 0, 1, 'L', fill=True)
    pdf.ln(3)
    pdf.set_font("Helvetica", "", 10)
    summary = safe_get(data, ['executive_summary'], 'No summary available.')
    pdf.multi_cell(0, 6, str(summary).encode('latin-1', 'replace').decode('latin-1'))
    pdf.ln(5)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "2. RISK ASSESSMENT", 0, 1, 'L', fill=True)
    pdf.ln(3)
    
    all_risks = safe_get(data, ['legal_risks'], []) + safe_get(data, ['hse_risks'], [])
    for item in all_risks:
        pdf.set_font("Helvetica", "B", 10)
        area = str(item.get('area', 'Risk')).encode('latin-1', 'replace').decode('latin-1')
        risk_level = str(item.get('risk_level', '-')).encode('latin-1', 'replace').decode('latin-1')
        pdf.cell(0, 6, f"{area} ({risk_level})", 0, 1)
        pdf.set_font("Helvetica", "", 10)
        finding = str(item.get('finding', '')).encode('latin-1', 'replace').decode('latin-1')
        pdf.multi_cell(0, 6, finding)
        pdf.ln(3)

    return pdf.output(dest='S').encode('latin-1', 'replace')

# ==========================================
# 🧠 ENGINE
# ==========================================

def extract_safe_text(uploaded_file):
    """
    Reads PDF and truncates to 50k chars to prevent API overload.
    """
    try:
        pdf_file = io.BytesIO(uploaded_file.getvalue())
        reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        # Safe Limit: First 20 pages + Last 10 pages
        total_pages = len(reader.pages)
        pages_to_read = list(range(min(20, total_pages))) 
        if total_pages > 20:
            pages_to_read += list(range(max(20, total_pages - 10), total_pages))
            
        for p in pages_to_read:
            chunk = reader.pages[p].extract_text()
            if chunk: text += chunk + "\n"
            
        return text[:50000] # Hard Cap
    except Exception as e:
        return f"ERROR_READING: {str(e)}"

def generate_with_retry(model, prompt, content):
    max_retries = 3
    base_delay = 5
    for attempt in range(max_retries):
        try:
            return model.generate_content(
                [prompt, content],
                generation_config={"response_mime_type": "application/json", "temperature": 0.0}
            )
        except exceptions.ResourceExhausted:
            time.sleep(base_delay * (2 ** attempt))
        except Exception as e:
            raise e
    return None

def process_file(uploaded_file, license_key):
    if not API_KEY or API_KEY == "MISSING_KEY": return None, "API Key Missing"
    
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(ACTIVE_MODEL)
    log_usage(license_key, uploaded_file.name, uploaded_file.size)
    
    with st.spinner("📄 Reading Document (Safe Mode)..."):
        text_content = extract_safe_text(uploaded_file)
        if str(text_content).startswith("ERROR"): return None, text_content
        
    master_prompt = "ACT AS A CONTRACT AUDITOR. Output JSON: " + SCHEMA_DEF + "\n\nDOCUMENT TEXT:\n" + text_content

    try:
        with st.spinner("🧠 Analyzing Risks..."):
            response = generate_with_retry(model, master_prompt, "")
            if response and response.text:
                return json.loads(response.text), None
            return None, "AI returned empty response."
    except Exception as e:
        return None, f"AI Error: {str(e)}"

# ==========================================
# 🖥️ UI
# ==========================================
def main():
    
    st.markdown("""
        <style>
        .stApp { background-color: #f8fafc; font-family: 'Inter', sans-serif; }
        .metric-card { background-color: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); text-align: center; }
        .metric-label { color: #64748b; font-size: 0.8rem; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; }
        .metric-value { color: #0f172a; font-size: 1.5rem; font-weight: 700; margin-top: 5px; }
        .risk-tag { padding: 4px 8px; border-radius: 6px; font-weight: 600; font-size: 0.8rem; color: white; display: inline-block;}
        .risk-high { background-color: #ef4444; }
        .risk-med { background-color: #f59e0b; }
        .risk-low { background-color: #10b981; }
        </style>
    """, unsafe_allow_html=True)

    if 'license_verified' not in st.session_state: st.session_state.license_verified = False
    if 'license_key' not in st.session_state: st.session_state.license_key = ""

    with st.sidebar:
        st.title(f"⚖️ {APP_NAME}")
        st.caption(f"Version: {APP_VERSION}")
        st.success("🟢 System Online")
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

        uploaded_file = st.file_uploader("Upload Contract", type=["pdf", "docx"])

    st.markdown(f"## {APP_NAME}")
    st.markdown("##### ⚡ Oil & Gas Specialist Edition")
    st.markdown("---")

    if uploaded_file:
        if st.button("Run Forensic Analysis"):
            data_dict, error = process_file(uploaded_file, st.session_state.license_key)
            if data_dict:
                st.session_state.analysis = data_dict
                st.rerun()
            else: 
                st.error(f"Processing Failed: {error}")

    if "analysis" in st.session_state:
        data = st.session_state.analysis
        
        c1, c2, c3, c4 = st.columns(4)
        score = safe_get(data, ['risk_score', 'score'], 0)
        level = safe_get(data, ['risk_score', 'level'], 'Unknown')
        comm_val = format_currency(safe_get(data, ['commercials', 'value_description'], "N/A"))
        law = safe_get(data, ['contract_details', 'governing_law'], "N/A")
        
        color = "#10b981" # Green
        if int(score) > 75: color = "#ef4444" # Red
        elif int(score) > 40: color = "#f59e0b" # Orange
        
        with c1: st.markdown(f"<div class='metric-card'><div class='metric-label'>Risk Score</div><div class='metric-value' style='color: {color};'>{score}/100</div><small>{level}</small></div>", unsafe_allow_html=True)
        with c2: st.markdown(f"<div class='metric-card'><div class='metric-label'>Value / Rate</div><div class='metric-value' style='font-size: 1.2rem;'>{comm_val}</div></div>", unsafe_allow_html=True)
        with c3: st.markdown(f"<div class='metric-card'><div class='metric-label'>Governing Law</div><div class='metric-value' style='font-size: 1.0rem;'>{law[:20]}...</div></div>", unsafe_allow_html=True)
        with c4: st.markdown(f"<div class='metric-card'><div class='metric-label'>Action</div><div class='metric-value' style='font-size: 1.2rem;'>{'⚠️ Review' if int(score) > 40 else '✅ Approved'}</div></div>", unsafe_allow_html=True)

        st.markdown("---")
        
        t1, t2, t3, t4, t5, t6 = st.tabs(["📄 Briefing", "💰 Commercials", "⚖️ Legal", "⛑️ HSE", "⚙️ Ops", "🚩 Compliance"])
        
        with t1:
            st.subheader("Executive Synthesis")
            st.markdown(safe_get(data, ['executive_summary']))
            st.info(f"Rationale: {safe_get(data, ['risk_score', 'rationale'])}")
            st.divider()
            pdf_bytes = create_pdf(data)
            st.download_button("📥 Download Enterprise Report (PDF)", pdf_bytes, "Assessment.pdf", "application/pdf")

        with t2:
            st.subheader("Commercial Terms")
            comm_data = safe_get(data, ['commercials'], {})
            if isinstance(comm_data, dict):
                for k, v in comm_data.items():
                    st.markdown(f"**{k.capitalize().replace('_', ' ')}:** {v}")
            else: st.markdown(comm_data)

        with t3:
            st.subheader("Legal Risk Vectors")
            risks = safe_get(data, ['legal_risks'], [])
            if risks:
                for r in risks:
                    r_col = "risk-high" if r.get('risk_level') == 'High' else "risk-med" if r.get('risk_level') == 'Medium' else "risk-low"
                    st.markdown(f"##### {r.get('area')} <span class='risk-tag {r_col}'>{r.get('risk_level')}</span>", unsafe_allow_html=True)
                    st.write(r.get('finding'))
                    st.caption(f"📝 Source: \"{r.get('source_text', 'N/A')}\"")
                    st.divider()
            else: st.info("No significant legal risks detected.")

        with t4:
            st.subheader("HSE & Safety Vectors")
            hse = safe_get(data, ['hse_risks'], [])
            if hse:
                for h in hse:
                    r_col = "risk-high" if h.get('risk_level') == 'High' else "risk-med" if h.get('risk_level') == 'Medium' else "risk-low"
                    st.markdown(f"##### {h.get('area')} <span class='risk-tag {r_col}'>{h.get('risk_level')}</span>", unsafe_allow_html=True)
                    st.write(h.get('finding'))
                    st.caption(f"📝 Source: \"{h.get('source_text', 'N/A')}\"")
                    st.divider()
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
