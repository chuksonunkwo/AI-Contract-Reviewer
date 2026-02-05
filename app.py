import streamlit as st
import os
import time
import json
import traceback

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
st.set_page_config(
    page_title="AI Contract Reviewer", 
    layout="wide", 
    page_icon="⚖️",
    initial_sidebar_state="expanded"
)

APP_VERSION = "13.0 (Self-Diagnostic)"
# WE USE THE SAFEST, MOST COMMON MODEL
ACTIVE_MODEL = "gemini-1.5-flash"

# ==========================================
# 🔧 SYSTEM DIAGNOSTICS (PRE-FLIGHT)
# ==========================================
SYSTEM_STATUS = {"lib": False, "key": False, "conn": False}

try:
    import google.generativeai as genai
    from fpdf import FPDF
    import PyPDF2
    import requests
    from google.api_core import exceptions
    import io
    SYSTEM_STATUS["lib"] = True
except ImportError as e:
    st.error(f"❌ CRITICAL ERROR: Library Missing. {e}")
    st.stop()

# 1. API KEY CHECK
try:
    API_KEY = os.environ.get("GEMINI_API_KEY")
    if not API_KEY:
        API_KEY = st.secrets["GEMINI_API_KEY"]
    SYSTEM_STATUS["key"] = True
    genai.configure(api_key=API_KEY)
except:
    API_KEY = None

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

def repair_json(json_str):
    json_str = re.sub(r"```json", "", json_str)
    json_str = re.sub(r"```", "", json_str)
    json_str = json_str.strip()
    return json_str

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
        self.cell(0, 10, f'CONFIDENTIAL // CONTRACT SENTINEL // v{APP_VERSION}', 0, 1, 'L')
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
    try:
        pdf_file = io.BytesIO(uploaded_file.getvalue())
        reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        # Read first 20 pages + Last 20 pages (Surgical Extraction)
        total_pages = len(reader.pages)
        pages_to_read = list(range(min(20, total_pages))) 
        if total_pages > 20:
            pages_to_read += list(range(max(20, total_pages - 20), total_pages))
            
        for p in pages_to_read:
            try:
                chunk = reader.pages[p].extract_text()
                if chunk: text += chunk + "\n"
            except: pass
            
        return text[:70000] # Safe Cap
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
    if not API_KEY: return None, "API Key Missing"
    
    # 1. Text Extraction
    with st.spinner("📄 Reading Document..."):
        text_content = extract_safe_text(uploaded_file)
        if str(text_content).startswith("ERROR"): return None, text_content
        
    master_prompt = "ACT AS A CONTRACT AUDITOR. Output JSON: " + SCHEMA_DEF + "\n\nDOCUMENT TEXT:\n" + text_content

    # 2. AI Analysis
    try:
        model = genai.GenerativeModel(ACTIVE_MODEL)
        with st.spinner(f"🧠 Analyzing with {ACTIVE_MODEL}..."):
            response = generate_with_retry(model, master_prompt, "")
            if response and response.text:
                return json.loads(repair_json(response.text)), None
            return None, "AI returned empty response."
    except Exception as e:
        # DETAILED ERROR REPORTING
        error_msg = str(e)
        if "404" in error_msg:
            return None, f"Model Error: {ACTIVE_MODEL} not found. Check Google API region."
        if "429" in error_msg:
            return None, "Rate Limit: Too many requests. Wait 60s."
        return None, f"System Error: {error_msg}"

# ==========================================
# 🖥️ UI
# ==========================================
def main():
    
    st.markdown("""
        <style>
        .stApp { background-color: #f8fafc; font-family: 'Inter', sans-serif; }
        .metric-card { background-color: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; text-align: center; }
        .metric-label { color: #64748b; font-size: 0.8rem; font-weight: 600; text-transform: uppercase; }
        .metric-value { color: #0f172a; font-size: 1.5rem; font-weight: 700; margin-top: 5px; }
        </style>
    """, unsafe_allow_html=True)

    with st.sidebar:
        st.title(f"⚖️ Contract Sentinel")
        st.caption(f"Version: {APP_VERSION}")
        
        st.markdown("### 🚦 System Status")
        if SYSTEM_STATUS["lib"]: st.success("📚 Libraries: OK")
        else: st.error("📚 Libraries: FAIL")
        
        if SYSTEM_STATUS["key"]: st.success("🔑 API Key: Found")
        else: st.error("🔑 API Key: MISSING")
        
        st.markdown("---")
        
        # Test Connection Button
        if st.button("Test AI Connection"):
            try:
                model = genai.GenerativeModel(ACTIVE_MODEL)
                response = model.generate_content("Say 'System Operational'")
                st.toast(f"✅ {response.text}")
            except Exception as e:
                st.error(f"Connection Failed: {e}")

        uploaded_file = st.file_uploader("Upload Contract", type=["pdf", "docx"])

    st.markdown(f"## {APP_NAME}")
    st.markdown("##### ⚡ Enterprise Edition")
    st.markdown("---")

    if uploaded_file:
        if st.button("Run Forensic Analysis"):
            data_dict, error = process_file(uploaded_file, "DEMO_USER")
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
        
        color = "#10b981" 
        if int(score) > 75: color = "#ef4444" 
        elif int(score) > 40: color = "#f59e0b" 
        
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
                    st.markdown(f"##### {r.get('area')} - {r.get('risk_level')}")
                    st.write(r.get('finding'))
                    st.caption(f"📝 Source: \"{r.get('source_text', 'N/A')}\"")
                    st.divider()
            else: st.info("No significant legal risks detected.")

        with t4:
            st.subheader("HSE & Safety Vectors")
            hse = safe_get(data, ['hse_risks'], [])
            if hse:
                for h in hse:
                    st.markdown(f"##### {h.get('area')} - {h.get('risk_level')}")
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
