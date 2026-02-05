import streamlit as st
import os
import traceback
import json
import time

# ==========================================
# 🛡️ CRASH PROTECTION & IMPORTS
# ==========================================
try:
    import google.generativeai as genai
    from fpdf import FPDF
    import PyPDF2
    import io
    import requests
    from google.api_core import exceptions
except ImportError as e:
    st.error(f"❌ CRITICAL: Library Missing. {e}")
    st.info("Please update requirements.txt on Render to include: streamlit, google-generativeai, fpdf, PyPDF2, requests")
    st.stop()

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
st.set_page_config(
    page_title="Contract AI", 
    layout="wide", 
    page_icon="⚖️",
    initial_sidebar_state="expanded"
)

APP_VERSION = "19.0 (Production 2.5 Pro)"
# ⚡ THE MODEL THAT WORKED
ACTIVE_MODEL = "gemini-2.0-flash" 
# NOTE: If 2.5-pro fails in future, switch this string to "models/gemini-1.5-pro"

# 1. API KEY
try:
    API_KEY = os.environ.get("GEMINI_API_KEY")
    if not API_KEY:
        API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    API_KEY = None

# 2. WEBHOOK & LICENSING (Optional)
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
    "governing_law": "string",
    "effective_date": "string"
  },
  "risk_score": {
    "score": 0-100,
    "level": "High/Medium/Low",
    "rationale": "string"
  },
  "executive_summary": "Markdown bullet points of key deal mechanics.",
  "commercials": {
    "value_description": "Extracted Rate/Value",
    "duration": "string",
    "termination_fee": "string",
    "payment_terms": "string"
  },
  "legal_risks": [
    { 
      "area": "Indemnity/Liability/Waiver", 
      "risk_level": "High/Med/Low", 
      "finding": "Summary of the risk", 
      "source_text": "Exact quote from contract" 
    }
  ],
  "hse_risks": [
    { 
      "area": "Stop Work/Safety Case/Environment", 
      "risk_level": "High/Med/Low", 
      "finding": "Summary of the risk", 
      "source_text": "Exact quote from contract" 
    }
  ],
  "compliance": {
    "local_content": "string",
    "sanctions": "string",
    "data_privacy": "string"
  },
  "operational_scope": {
    "scope_summary": "string",
    "key_equipment": "string"
  }
}
"""

# ==========================================
# 🛠️ UTILITIES
# ==========================================

def repair_json(json_str):
    json_str = json_str.replace("```json", "").replace("```", "").strip()
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
# 📄 PDF ENGINE
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

    # Risk Table
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "2. RISK & LIABILITY", 0, 1, 'L', fill=True)
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
        
        # Source text
        source = str(item.get('source_text', '')).encode('latin-1', 'replace').decode('latin-1')
        if source and len(source) > 5:
            pdf.set_font("Helvetica", "I", 8)
            pdf.set_text_color(100, 100, 100)
            pdf.multi_cell(0, 5, f"Source: {source}")
            pdf.set_text_color(0, 0, 0)
            
        pdf.ln(3)

    return pdf.output(dest='S').encode('latin-1', 'replace')

# ==========================================
# 🖥️ UI & LOGIC
# ==========================================
def main():
    
    # CSS for Professional Look
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

    with st.sidebar:
        st.title("⚖️ Contract Sentinel")
        st.caption(f"Version: {APP_VERSION}")
        
        if API_KEY:
            st.success(f"✅ AI Active: {ACTIVE_MODEL}")
        else:
            st.error("❌ API Key Missing")
            
        st.markdown("---")
        uploaded_file = st.file_uploader("Upload Contract (PDF)", type=["pdf", "docx"])

    st.markdown("## Strategic Contract Assessment")
    st.markdown("##### ⚡ Oil & Gas Specialist Edition")
    st.markdown("---")

    if uploaded_file and st.button("Run Forensic Analysis"):
        if not API_KEY:
            st.error("CRITICAL: API Key is missing.")
            st.stop()

        genai.configure(api_key=API_KEY)
        
        # -- STEP A: READ PDF (Safe Mode) --
        text = ""
        with st.spinner("📄 Reading PDF..."):
            try:
                pdf_file = io.BytesIO(uploaded_file.getvalue())
                reader = PyPDF2.PdfReader(pdf_file)
                # Limit to first 40 pages to prevent token overflow/timeout
                for i in range(min(len(reader.pages), 40)):
                    page_text = reader.pages[i].extract_text()
                    if page_text: text += page_text + "\n"
            except Exception as e:
                st.error(f"PDF Error: {e}")
                st.stop()

        # -- STEP B: ANALYZE --
        with st.spinner(f"🧠 Analyzing with {ACTIVE_MODEL}..."):
            
            prompt = """
            ACT AS A FORENSIC CONTRACT AUDITOR. Review this contract text.
            You MUST output your analysis in this STRICT JSON FORMAT:
            """ + SCHEMA_DEF + """
            
            CRITICAL INSTRUCTIONS:
            1. Extract the Risk Score (0-100).
            2. Find the Indemnity/Liability clauses. Quote the specific text in 'source_text'.
            3. Find the Commercial terms (Values, Termination Fees).
            
            CONTRACT TEXT:
            """ + text[:50000] # Safe char limit

            try:
                model = genai.GenerativeModel(ACTIVE_MODEL)
                response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
                
                if response.text:
                    try:
                        data = json.loads(response.text)
                        st.session_state.analysis = data # Save to session
                        st.rerun() # Refresh to show dashboard
                    except json.JSONDecodeError:
                        st.error("AI Output Error: Could not parse JSON.")
                        st.write(response.text)
                else:
                    st.error("AI returned empty response.")
                    
            except Exception as e:
                st.error(f"Analysis Failed: {e}")

    # -- STEP C: DISPLAY DASHBOARD --
    if "analysis" in st.session_state:
        data = st.session_state.analysis
        
        # 1. HERO METRICS
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
        
        # 2. TABS
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
            st.subheader("Legal Risk Vectors (Contractual)")
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
