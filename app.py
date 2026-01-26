import streamlit as st
import google.generativeai as genai
import PyPDF2
import docx
from fpdf import FPDF
from io import StringIO
import datetime
import json
import time
import re
import pandas as pd
import os
import requests
import ast
import gc

# ==========================================
# ⚙️ CONFIGURATION & SECRETS
# ==========================================
ACTIVE_MODEL = "gemini-2.0-flash-exp"
APP_VERSION = "2.2.0 (Enterprise Speed-Tuned)"

# Tuning the "Chunking Engine"
CHUNK_SIZE = 80000      # Increased to ~30 pages for speed
OVERLAP_SIZE = 2000     # Overlap to catch clauses cut between chunks

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
# 🛠️ HELPER FUNCTIONS (JSON REPAIR)
# ==========================================

def repair_json(json_str):
    """Auto-heals broken JSON if the AI gets cut off."""
    json_str = json_str.strip()
    json_str = re.sub(r"```[a-zA-Z]*", "", json_str).replace("```", "")
    
    open_braces = json_str.count('{')
    close_braces = json_str.count('}')
    open_brackets = json_str.count('[')
    close_brackets = json_str.count(']')
    
    json_str += ']' * (open_brackets - close_brackets)
    json_str += '}' * (open_braces - close_braces)
    
    return json_str

def extract_json(text):
    """Robust JSON Extractor v4"""
    try:
        text = re.sub(r"```[a-zA-Z]*", "", text).replace("```", "")
        start = text.find('{')
        end = text.rfind('}') + 1
        
        if start == -1: return None
        json_str = text[start:] if end <= start else text[start:end]
        
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            try:
                return json.loads(repair_json(json_str))
            except:
                try:
                    return ast.literal_eval(json_str)
                except:
                    return None
    except:
        return None

def check_gumroad_license(key):
    url = "https://api.gumroad.com/v2/licenses/verify"
    params = {"product_id": GUMROAD_PRODUCT_ID, "license_key": key, "increment_uses_count": "false"}
    try:
        response = requests.post(url, data=params)
        data = response.json()
        if not data.get("success"): return False, "❌ Invalid License Key."
        purchase = data.get("purchase", {})
        if purchase.get("refunded") or purchase.get("chargebacked"): return False, "⛔ Access denied: Refunded."
        if purchase.get("subscription_cancelled_at"): return False, "⚠️ Subscription Cancelled."
        if purchase.get("subscription_failed_at"): return False, "⚠️ Payment Failed."
        return True, "✅ Access Granted"
    except Exception as e: return False, f"Connection Error: {str(e)}"

def log_usage(license_key, filename, file_size):
    if not DISCORD_WEBHOOK: return
    masked_key = f"****{license_key[-4:]}" if len(license_key) > 4 else "Unknown"
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    size_mb = round(file_size / (1024 * 1024), 2)
    message = {"content": f"🚨 **Analysis Run**\n👤 **User:** `{masked_key}`\n📄 **File:** `{filename}` ({size_mb} MB)\n⏰ **Time:** {timestamp}"}
    try: requests.post(DISCORD_WEBHOOK, json=message)
    except: pass

def safe_get(data, path, default="N/A"):
    try:
        current = data
        for key in path:
            if isinstance(current, list):
                if len(current) > 0: current = current[0]
                else: return default
            elif isinstance(current, dict):
                current = current.get(key, default)
            else: return default
        return current
    except: return default

def clean_text(text):
    if not isinstance(text, str): return str(text)
    return text.encode('latin-1', 'ignore').decode('latin-1')

# ==========================================
# 📄 PDF ENGINE (UPDATED FOR 4 PILLARS)
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
    pdf.multi_cell(0, 8, clean_text(title), 0, 'L')
    pdf.ln(5)
    
    # Score
    pdf.set_font("Helvetica", "", 10)
    score = safe_get(data, ['riskScore', 'score'])
    pdf.cell(0, 8, f"Date: {datetime.date.today()} | Risk Score: {score}/100", 0, 1, 'L')
    pdf.ln(5)
    
    # 1. Exec Summary
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "1. EXECUTIVE SYNTHESIS", 0, 1, 'L', fill=True)
    pdf.ln(3)
    pdf.set_font("Helvetica", "", 10)
    summary = safe_get(data, ['executiveSummary'], 'No summary available.')
    pdf.multi_cell(0, 6, clean_text(summary))
    pdf.ln(5)

    # 2. Commercials
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "2. COMMERCIAL TERMS", 0, 1, 'L', fill=True)
    pdf.ln(3)
    pdf.set_font("Helvetica", "", 10)
    comm_terms = safe_get(data, ['commercials'], {})
    if isinstance(comm_terms, dict):
        for key, value in comm_terms.items():
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(40, 6, f"{key.capitalize()}:", 0, 0)
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, 6, clean_text(str(value)))
            pdf.ln(1)
    else:
        pdf.multi_cell(0, 6, clean_text(str(comm_terms)))
    pdf.ln(5)

    # 3. Legal & Risk
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "3. LEGAL RISK VECTORS", 0, 1, 'L', fill=True)
    pdf.ln(3)
    risks = safe_get(data, ['riskTable'], [])
    for item in risks:
        pdf.set_font("Helvetica", "B", 10)
        area = clean_text(item.get('area', 'Risk'))
        risk_level = clean_text(item.get('risk', '-'))
        pdf.cell(0, 6, f"{area} ({risk_level})", 0, 1)
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 6, clean_text(item.get('finding', '')))
        pdf.ln(3)
    pdf.ln(5)

    # 4. Tech & Ops (NEW)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "4. OPERATIONAL & TECHNICAL SPECS", 0, 1, 'L', fill=True)
    pdf.ln(3)
    ops = safe_get(data, ['operationalTable'], [])
    for item in ops:
        pdf.set_font("Helvetica", "B", 10)
        area = clean_text(item.get('area', 'Spec'))
        pdf.cell(0, 6, f"{area}", 0, 1)
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 6, clean_text(item.get('finding', '')))
        pdf.ln(3)
    pdf.ln(5)

    # 5. Compliance (NEW)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "5. COMPLIANCE & REGULATORY", 0, 1, 'L', fill=True)
    pdf.ln(3)
    comp = safe_get(data, ['complianceTable'], [])
    for item in comp:
        pdf.set_font("Helvetica", "B", 10)
        area = clean_text(item.get('area', 'Rule'))
        pdf.cell(0, 6, f"{area}", 0, 1)
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 6, clean_text(item.get('finding', '')))
        pdf.ln(3)

    return pdf.output(dest='S').encode('latin-1', 'replace')

# ==========================================
# 🧠 AI ENGINE (4-PILLAR ARCHITECTURE)
# ==========================================

# 1. The "Universal Scan" Prompt (4 Pillars)
MAP_PROMPT = """
You are a Senior Contract Analyst. Analyze this section of the contract (Text provided below).
The text includes page markers [=== PAGE X ===]. Always cite these page numbers in your findings.

Extract and categorize findings into this JSON structure:
{
  "commercial_findings": [
    {"topic": "Price/Rate", "details": "string", "citation": "Page X"},
    {"topic": "Duration/Term", "details": "string", "citation": "Page X"},
    {"topic": "Penalties/LDs", "details": "string", "citation": "Page X"}
  ],
  "legal_findings": [
    {"topic": "Indemnity", "risk": "High/Med/Low", "details": "string", "citation": "Page X"},
    {"topic": "Termination", "risk": "High/Med/Low", "details": "string", "citation": "Page X"},
    {"topic": "Liability Cap", "risk": "High/Med/Low", "details": "string", "citation": "Page X"}
  ],
  "operational_findings": [
    {"topic": "Scope of Work", "details": "string", "citation": "Page X"},
    {"topic": "Equipment Specs", "details": "string", "citation": "Page X"},
    {"topic": "HSE/Performance", "details": "string", "citation": "Page X"}
  ],
  "compliance_findings": [
    {"topic": "Local Content", "details": "string", "citation": "Page X"},
    {"topic": "Sanctions", "details": "string", "citation": "Page X"},
    {"topic": "Anti-Bribery", "details": "string", "citation": "Page X"}
  ],
  "parties_found": ["string"]
}
If a section is empty, leave the list empty. Do not hallucinate.
"""

# 2. The "Synthesis" Prompt (Weighed Scoring)
REDUCE_PROMPT = """
You are the Chief Legal Officer. Merge these partial findings into a Final Strategic Report.

RULES for Synthesis:
1. CROSS-CHECK: Move financial values found in Legal/Ops to Commercials.
2. RISK SCORING: Calculate risk (0-100) considering NOT just Legal, but also Operational (e.g. impossible specs) and Compliance (e.g. Local Content) risks.
3. CITATIONS: Keep the [Page X] citations.

Return ONLY this Final JSON:
{
  "contractDetails": { "title": "string", "parties": ["string"] },
  "riskScore": { "score": 0-100, "level": "High/Medium/Low", "rationale": "Why this score?" },
  "executiveSummary": "Detailed summary with bullet points and citations [Page X].",
  "commercials": { 
      "value": "Total value or rate structure with citations", 
      "duration": "Effective date, term, and renewal options with citations"
  },
  "riskTable": [
      { "area": "string", "risk": "High/Med/Low", "finding": "string with citation [Page X]" }
  ],
  "operationalTable": [
      { "area": "string", "finding": "string with citation [Page X]" }
  ],
  "complianceTable": [
      { "area": "string", "finding": "string with citation [Page X]" }
  ],
  "deepDive": "Comprehensive Markdown report integrating all sections. Use headers (##)."
}
"""

COACH_INSTRUCTION = "You are a Negotiation Coach. Explain the risk, draft a redline, and provide a negotiation argument."

def process_file_with_markers(uploaded_file):
    text = ""
    try:
        if "pdf" in uploaded_file.type:
            reader = PyPDF2.PdfReader(uploaded_file)
            for i, page in enumerate(reader.pages):
                page_content = page.extract_text()
                if page_content:
                    text += f"\n\n[=== PAGE {i+1} ===]\n{page_content}"
            gc.collect()
            return text
        elif "word" in uploaded_file.type:
            doc = docx.Document(uploaded_file)
            for i, para in enumerate(doc.paragraphs):
                if i % 20 == 0:
                    text += f"\n\n[=== SECTION {int(i/20)+1} ===]\n"
                text += para.text + "\n"
            gc.collect()
            return text
        elif "text" in uploaded_file.type:
            return StringIO(uploaded_file.getvalue().decode("utf-8")).read()
    except: return None
    return None

def analyze_contract_map_reduce(full_text, filename, file_size, license_key):
    if not API_KEY or API_KEY == "MISSING_KEY":
        st.error("⚠️ System Error: API Key missing.")
        return None
    
    log_usage(license_key, filename, file_size)
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(ACTIVE_MODEL)
    
    # Chunking
    total_len = len(full_text)
    chunks = []
    start = 0
    while start < total_len:
        end = min(start + CHUNK_SIZE, total_len)
        if end < total_len:
            next_newline = full_text.find('\n', end)
            if next_newline != -1 and next_newline - end < 500: end = next_newline
        chunks.append(full_text[start:end])
        start = end - OVERLAP_SIZE
    
    # Map Phase
    partial_results = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    total_chunks = len(chunks)
    
    for i, chunk in enumerate(chunks):
        status_text.text(f"🧠 Universal Scan: Section {i+1} of {total_chunks}...")
        progress_bar.progress(int((i / total_chunks) * 80))
        try:
            config = genai.types.GenerationConfig(response_mime_type="application/json", temperature=0.0)
            response = model.generate_content(f"{MAP_PROMPT}\n\nDATA:\n{chunk}", generation_config=config)
            extracted = extract_json(response.text)
            if extracted: partial_results.append(json.dumps(extracted))
            del response; gc.collect()
        except: continue

    # Reduce Phase
    status_text.text("✨ Synthesizing 4-Pillar Report (Cross-checking Vectors)...")
    progress_bar.progress(90)
    try:
        combined_data = "\n---\n".join(partial_results)
        if len(combined_data) > 800000: combined_data = combined_data[:800000]
        config = genai.types.GenerationConfig(response_mime_type="application/json", temperature=0.0)
        final_response = model.generate_content(f"{REDUCE_PROMPT}\n\nEXTRACTED DATA:\n{combined_data}", generation_config=config)
        progress_bar.progress(100)
        status_text.text("✅ Analysis Complete")
        return final_response.text
    except Exception as e:
        st.error(f"Synthesis Error: {str(e)}")
        return None

# ==========================================
# 🖥️ MAIN UI (ENTERPRISE DASHBOARD)
# ==========================================
def main():
    st.set_page_config(page_title="Strategic Contract Assessment", layout="wide", page_icon="🛡️")
    
    # Premium CSS
    st.markdown("""
        <style>
        .stApp { background-color: #f8fafc; font-family: 'Inter', sans-serif; }
        .metric-card { background-color: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); text-align: center; }
        .metric-label { color: #64748b; font-size: 0.8rem; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; }
        .metric-value { color: #0f172a; font-size: 1.8rem; font-weight: 700; margin-top: 5px; }
        .risk-badge { padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 0.8rem; }
        </style>
    """, unsafe_allow_html=True)

    if 'license_verified' not in st.session_state: st.session_state.license_verified = False
    if 'license_key' not in st.session_state: st.session_state.license_key = ""

    with st.sidebar:
        st.title("🛡️ Secure Portal")
        st.caption(f"System: {APP_VERSION}")
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
            st.info("👤 User Authenticated")
            if st.button("End Session"):
                st.session_state.license_verified = False
                st.rerun()
            st.markdown("---")

        uploaded_file = st.file_uploader("Upload Agreement", type=["pdf", "docx", "txt"])
        if uploaded_file: st.markdown(f"**File:** `{uploaded_file.name}`")

    st.markdown("## Strategic Contract Assessment")
    st.markdown("##### ⚡ Oil & Gas Specialist Edition")
    st.markdown("---")

    if uploaded_file:
        if "file_data" not in st.session_state:
            with st.spinner("Processing document structure..."):
                text = process_file_with_markers(uploaded_file)
                if text: 
                    st.session_state.file_data = text
                    if len(text) > 2000000: st.warning("⚠️ Large File Detected. Enabling Enterprise Processing Mode.")
                else: st.error("Corrupt file."); st.stop()

        if st.button("Initialize Enterprise Analysis"):
            raw_response = analyze_contract_map_reduce(
                st.session_state.file_data,
                filename=uploaded_file.name,
                file_size=uploaded_file.size,
                license_key=st.session_state.license_key
            )
            
            if raw_response:
                data_dict = extract_json(raw_response)
                if data_dict:
                    st.session_state.analysis = data_dict
                    st.rerun()
                else:
                    st.warning("⚠️ Structure Parse Warning: Switching to Raw View")
                    st.session_state.analysis = {"riskScore": {"score": 0}, "executiveSummary": raw_response}
                    st.rerun()
            else: st.error("Processing Failed.")

    if "analysis" in st.session_state:
        data = st.session_state.analysis
        
        # HERO METRICS ROW
        c1, c2, c3, c4 = st.columns(4)
        score = safe_get(data, ['riskScore', 'score'], 0)
        level = safe_get(data, ['riskScore', 'level'], 'Unknown')
        
        color = "#10b981" # Green
        if int(score) > 75: color = "#ef4444" # Red
        elif int(score) > 40: color = "#f59e0b" # Orange
        
        comm_val = safe_get(data, ['commercials', 'value'], "N/A")
        if isinstance(comm_val, str) and len(comm_val) > 20: comm_val = "See Details"
        
        with c1: st.markdown(f"<div class='metric-card'><div class='metric-label'>Risk Score</div><div class='metric-value' style='color: {color};'>{score}/100</div><small>{level}</small></div>", unsafe_allow_html=True)
        with c2: st.markdown(f"<div class='metric-card'><div class='metric-label'>Contract Value</div><div class='metric-value'>{comm_val}</div></div>", unsafe_allow_html=True)
        with c3: st.markdown(f"<div class='metric-card'><div class='metric-label'>Entity</div><div class='metric-value' style='font-size: 1rem;'>{safe_get(data, ['compliance', 'entity'], 'N/A')}</div></div>", unsafe_allow_html=True)
        with c4: st.markdown(f"<div class='metric-card'><div class='metric-label'>Action</div><div class='metric-value' style='font-size: 1rem;'>{'⚠️ Review' if int(score) > 40 else '✅ Approved'}</div></div>", unsafe_allow_html=True)

        st.markdown("---")
        
        # 5-TAB ENTERPRISE LAYOUT
        t1, t2, t3, t4, t5, t6 = st.tabs(["📄 Briefing", "💰 Commercials", "⚖️ Legal", "⚙️ Tech/Ops", "🚩 Compliance", "💬 Chat"])
        
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
            comp = safe_get(data, ['complianceTable'], [])
            if comp: st.dataframe(pd.DataFrame(comp), use_container_width=True, hide_index=True)
            else: st.info("No compliance flags detected.")

        with t6:
            st.subheader("🤖 Clause Explorer")
            if "messages" not in st.session_state: st.session_state.messages = []
            for msg in st.session_state.messages:
                with st.chat_message(msg["role"]): st.markdown(msg["content"])
            if prompt := st.chat_input("Ask about a specific clause..."):
                st.session_state.messages.append({"role": "user", "content": prompt})
                with st.chat_message("user"): st.markdown(prompt)
                with st.chat_message("assistant"):
                    with st.spinner("Analyzing..."):
                        genai.configure(api_key=API_KEY)
                        chat_model = genai.GenerativeModel(ACTIVE_MODEL, system_instruction=COACH_INSTRUCTION)
                        full_prompt = f"Contract Context: {st.session_state.file_data[:30000]}\\n\\nUser Question: {prompt}"
                        response = chat_model.generate_content(full_prompt)
                        st.markdown(response.text)
                        st.session_state.messages.append({"role": "assistant", "content": response.text})

if __name__ == "__main__":
    main()
