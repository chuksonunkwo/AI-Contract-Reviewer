import streamlit as st
import google.generativeai as genai
import PyPDF2
import docx
from io import StringIO
import io
import json
import re
import pandas as pd
import os
import requests
import ast
import gc

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
# 1. SERVER CONFIGURATION
st.set_page_config(
    page_title="Strategic Contract Assessment", 
    layout="wide", 
    page_icon="🛡️",
    initial_sidebar_state="expanded"
)

# 2. CONSTANTS
ACTIVE_MODEL = "gemini-2.0-flash-exp"
APP_VERSION = "3.0.0 (Ultra-Stable)"

# ⚡ SAFETY LIMITS (The "Crash Prevention" System)
# We start with 30 pages. If this works, you can increase to 50.
MAX_PAGES_TO_READ = 30  
CHUNK_SIZE = 60000      # Characters per chunk

# 3. API KEY
try:
    API_KEY = os.environ.get("GEMINI_API_KEY")
    if not API_KEY:
        API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    API_KEY = "MISSING_KEY"

# 4. WEBHOOK
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
            "content": f"🚨 **Run:** `{filename}` ({round(file_size/1024/1024,1)}MB) | User: `{license_key[-4:]}`"
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

# ==========================================
# 🧠 AI PROMPTS
# ==========================================
MAP_PROMPT = """
Analyze this contract section. Text includes [=== PAGE X ===] markers. Cite them.
Extract to JSON:
{
  "commercial_findings": [{"topic": "Price/Rate/Term", "details": "string", "citation": "Page X"}],
  "legal_findings": [{"topic": "Indemnity/Liability", "risk": "High/Med/Low", "details": "string", "citation": "Page X"}],
  "compliance_findings": [{"topic": "Local Content/Sanctions", "details": "string", "citation": "Page X"}]
}
"""

REDUCE_PROMPT = """
Merge findings into a Final Report.
JSON Output:
{
  "riskScore": { "score": 0-100, "level": "High/Med/Low" },
  "executiveSummary": "Bullet points with [Page X] citations.",
  "commercials": { "value": "string", "duration": "string" },
  "riskTable": [{ "area": "string", "risk": "High/Med/Low", "finding": "string" }],
  "complianceTable": [{ "area": "string", "finding": "string" }],
  "deepDive": "Markdown report."
}
"""

# ==========================================
# 📄 PROCESSING ENGINE
# ==========================================
def process_file_optimized(uploaded_file):
    """
    Reads PDF page-by-page and discards memory immediately.
    Stops exactly at MAX_PAGES_TO_READ.
    """
    text = ""
    try:
        if "pdf" in uploaded_file.type:
            # Load file into stream
            pdf_stream = io.BytesIO(uploaded_file.getvalue())
            reader = PyPDF2.PdfReader(pdf_stream)
            
            # Hard limit calculation
            limit = min(len(reader.pages), MAX_PAGES_TO_READ)
            
            for i in range(limit):
                page = reader.pages[i]
                text += f"\n\n[=== PAGE {i+1} ===]\n{page.extract_text()}"
                
                # Free memory per page
                del page
            
            if len(reader.pages) > limit:
                text += "\n\n[=== END OF ANALYSIS (CAP REACHED) ===]"
                
            # Cleanup
            del reader
            del pdf_stream
            gc.collect()
            return text
            
        else:
            # Fallback for Word/Text
            return StringIO(uploaded_file.getvalue().decode("utf-8", errors="ignore")).read()[:300000]
            
    except Exception as e:
        return f"Error reading file: {str(e)}"

def analyze_contract(full_text, filename, file_size, license_key):
    if not API_KEY or API_KEY == "MISSING_KEY": return None
    log_usage(license_key, filename, file_size)
    
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(ACTIVE_MODEL)
    
    # Simple chunking
    chunks = [full_text[i:i+CHUNK_SIZE] for i in range(0, len(full_text), CHUNK_SIZE)]
    partial_results = []
    
    progress_bar = st.progress(0)
    status = st.empty()
    
    # Map
    for i, chunk in enumerate(chunks):
        status.text(f"Scanning Section {i+1}/{len(chunks)}...")
        progress_bar.progress((i / len(chunks)) * 0.8)
        try:
            response = model.generate_content(f"{MAP_PROMPT}\nDATA:\n{chunk}")
            if extract_json(response.text):
                partial_results.append(response.text)
            del response
            gc.collect()
        except: pass
        
    # Reduce
    status.text("Synthesizing Report...")
    progress_bar.progress(0.9)
    try:
        combined = "\n".join(partial_results)[:500000] # Safety cap
        final = model.generate_content(f"{REDUCE_PROMPT}\nDATA:\n{combined}")
        progress_bar.progress(1.0)
        return final.text
    except: return None

# ==========================================
# 🖥️ UI
# ==========================================
def main():
    # Custom CSS for "Enterprise Look"
    st.markdown("""
        <style>
        .stApp { background-color: #f8fafc; }
        .metric-box { background: white; padding: 15px; border-radius: 10px; border: 1px solid #e2e8f0; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
        .metric-lbl { font-size: 0.8rem; color: #64748b; font-weight: 600; text-transform: uppercase; }
        .metric-val { font-size: 1.5rem; font-weight: 700; color: #0f172a; }
        </style>
    """, unsafe_allow_html=True)

    if 'auth' not in st.session_state: st.session_state.auth = False

    with st.sidebar:
        st.title("🛡️ Contract AI")
        st.caption(f"v{APP_VERSION}")
        if not st.session_state.auth:
            key = st.text_input("License Key", type="password")
            if st.button("Login"):
                valid, msg = check_gumroad_license(key)
                if valid:
                    st.session_state.auth = True
                    st.session_state.key = key
                    st.rerun()
                else: st.error(msg)
            st.stop()
        
        if st.button("Logout"):
            st.session_state.auth = False
            st.rerun()
            
        uploaded_file = st.file_uploader("Upload Contract", type=["pdf", "docx"])

    st.title("Strategic Contract Assessment")
    st.markdown("##### ⚡ Oil & Gas Specialist Edition")

    if uploaded_file:
        if st.button("Run Analysis"):
            with st.spinner("Processing..."):
                text = process_file_optimized(uploaded_file)
                if text and len(text) > 100:
                    raw_res = analyze_contract(text, uploaded_file.name, uploaded_file.size, st.session_state.key)
                    if raw_res:
                        data = extract_json(raw_res)
                        if data: st.session_state.data = data
                        else: st.error("AI Output Error. Please try again.")
                    else: st.error("Analysis Timeout.")
                else: st.error("Could not read file text.")

    if 'data' in st.session_state:
        data = st.session_state.data
        
        # Metrics
        c1, c2, c3 = st.columns(3)
        score = safe_get(data, ['riskScore', 'score'], 0)
        col = "#10b981" if int(score) < 40 else "#ef4444"
        
        with c1: st.markdown(f"<div class='metric-box'><div class='metric-lbl'>Risk Score</div><div class='metric-val' style='color:{col}'>{score}/100</div></div>", unsafe_allow_html=True)
        with c2: st.markdown(f"<div class='metric-box'><div class='metric-lbl'>Value</div><div class='metric-val'>{str(safe_get(data, ['commercials', 'value']))[:15]}</div></div>", unsafe_allow_html=True)
        with c3: st.markdown(f"<div class='metric-box'><div class='metric-lbl'>Duration</div><div class='metric-val'>{str(safe_get(data, ['commercials', 'duration']))[:15]}</div></div>", unsafe_allow_html=True)
        
        st.markdown("---")
        
        t1, t2, t3, t4 = st.tabs(["📄 Executive Summary", "⚖️ Legal Risks", "🚩 Compliance", "📝 Deep Dive"])
        
        with t1: st.markdown(safe_get(data, ['executiveSummary']))
        
        with t2:
            risks = safe_get(data, ['riskTable'], [])
            if risks: st.dataframe(pd.DataFrame(risks), use_container_width=True)
            
        with t3:
            comp = safe_get(data, ['complianceTable'], [])
            if comp: st.dataframe(pd.DataFrame(comp), use_container_width=True)
            
        with t4: st.markdown(safe_get(data, ['deepDive']))

if __name__ == "__main__":
    main()
