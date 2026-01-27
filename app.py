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

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
st.set_page_config(
    page_title="Strategic Contract Assessment", 
    layout="wide", 
    page_icon="🛡️",
    initial_sidebar_state="expanded"
)

# ⚡ CORE ENGINE: Switched back to Gemini 2.0 as requested
ACTIVE_MODEL = "gemini-2.0-flash-exp"
APP_VERSION = "4.1.0 (Gemini 2.0 Cloud Direct)"

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
    json_str = re.sub(r"```[a-zA-Z]*", "", json_str).replace("```", "").strip()
    return json_str + ']' * (json_str.count('[') - json_str.count(']')) + '}' * (json_str.count('{') - json_str.count('}'))

def extract_json(text):
    try:
        text = re.sub(r"```[a-zA-Z]*", "", text).replace("```", "")
        start, end = text.find('{'), text.rfind('}') + 1
        if start == -1: return None
        json_str = text[start:] if end <= start else text[start:end]
        try: return json.loads(json_str)
        except: 
            try: return json.loads(repair_json(json_str))
            except: return ast.literal_eval(json_str)
    except: return None

def safe_get(data, path, default="N/A"):
    try:
        for key in path:
            if isinstance(data, list): data = data[0] if data else default
            elif isinstance(data, dict): data = data.get(key, default)
            else: return default
        return data
    except: return default

def format_currency(value):
    """Clean up messy money strings for the dashboard cards"""
    if not isinstance(value, str): return str(value)
    if len(value) > 20: return "See Report" 
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
# 🧠 CLOUD ENGINE (NO LOCAL PROCESSING)
# ==========================================

MASTER_PROMPT = """
You are a Senior Contract Analyst. I have uploaded a contract file. 
Scan the ENTIRE document from Page 1 to the final Appendix.

Your Job: Extract critical Commercial, Legal, Operational, and Compliance data.

CRITICAL INSTRUCTIONS:
1. COMMERCIALS: Look for the "Schedule of Rates" or "Compensation" usually in the Appendices (Back of doc). Find the specific Daily Rates, Mob Fees, and Termination Fees.
2. COMPLIANCE: Look for "Local Content" or "National Content" clauses (Namibia/Africa specific).
3. OPERATIONS: Look for Technical Specs (Drillship specs, BOP rating).

Output strictly valid JSON:
{
  "contractDetails": { "title": "string", "parties": ["string"] },
  "riskScore": { "score": 0-100, "level": "High/Med/Low", "rationale": "Short reason" },
  "executiveSummary": "Bullet points highlighting value, major risks, and operational scope.",
  "commercials": { 
      "value": "Total Est. Value OR Day Rate (e.g. $350k/day)", 
      "duration": "e.g. 2 Wells + 1 Option",
      "terminationFee": "e.g. 50% of Day Rate"
  },
  "compliance": {
      "entity": "string",
      "sanctions": { "status": "Clean/Flagged", "details": "string" },
      "localContent": "Summary of local hiring/purchasing requirements"
  },
  "riskTable": [
      { "area": "Indemnity", "risk": "High/Med/Low", "finding": "Knock-for-knock details" },
      { "area": "Liability Cap", "risk": "High/Med/Low", "finding": "Cap amount (e.g. $5M)" },
      { "area": "Consequential Loss", "risk": "High/Med/Low", "finding": "Waiver details" }
  ],
  "operationalTable": [
      { "area": "Scope", "finding": "e.g. Drilling 2 wells in Block X" },
      { "area": "Equipment", "finding": "e.g. Drillship DP3" }
  ],
  "deepDive": "Detailed Markdown report."
}
"""

def process_file_cloud(uploaded_file, license_key):
    """
    Uploads file DIRECTLY to Google Gemini. 
    Bypasses local parsing to prevent RAM crashes.
    """
    if not API_KEY or API_KEY == "MISSING_KEY": return None, "API Key Missing"
    
    log_usage(license_key, uploaded_file.name, uploaded_file.size)
    genai.configure(api_key=API_KEY)
    
    # 1. Save to Temp File (Low RAM usage)
    try:
        suffix = ".pdf" if uploaded_file.type == "application/pdf" else ".docx"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            tmp_path = tmp_file.name
            
        # 2. Upload to Google Cloud
        with st.spinner("☁️ Uploading to Neural Engine (This takes 10s)..."):
            g_file = genai.upload_file(tmp_path, mime_type=uploaded_file.type)
            
            # Wait for processing
            while g_file.state.name == "PROCESSING":
                time.sleep(2)
                g_file = genai.get_file(g_file.name)
                
        # 3. Analyze
        with st.spinner("🧠 Analyzing 100% of Document Context..."):
            model = genai.GenerativeModel(ACTIVE_MODEL)
            response = model.generate_content(
                [MASTER_PROMPT, g_file],
                generation_config={"response_mime_type": "application/json"}
            )
            
        # 4. Cleanup
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
        
        # Formatting to prevent UI overflow
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
        t1, t2, t3, t4, t5 = st.tabs(["📄 Briefing", "💰 Commercials", "⚖️ Legal", "⚙️ Ops", "🚩 Compliance"])
        
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
            st.subheader("Legal Risk Vectors")
            risks = safe_get(data, ['riskTable'], [])
            if risks: st.dataframe(pd.DataFrame(risks), use_container_width=True, hide_index=True)
            else: st.info("No significant legal risks detected.")

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
                    if isinstance(v, dict): st.write(f"**{k}:**", v) # Handle nested dicts like sanctions
                    else: st.markdown(f"**{k.capitalize()}:** {v}")
            else: st.markdown(comp)

if __name__ == "__main__":
    main()
