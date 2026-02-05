import streamlit as st
import os
import traceback

# ==========================================
# 🛡️ CRASH PROTECTION & IMPORTS
# ==========================================
try:
    import google.generativeai as genai
    from fpdf import FPDF
    import PyPDF2
    import io
    import json
    import time
    from google.api_core import exceptions
except ImportError as e:
    st.error(f"❌ CRITICAL: Library Missing. {e}")
    st.stop()

# ==========================================
# ⚙️ CONFIG
# ==========================================
st.set_page_config(page_title="Contract AI", page_icon="⚖️")

# 1. API KEY
try:
    API_KEY = os.environ.get("GEMINI_API_KEY")
    if not API_KEY:
        API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    API_KEY = None

# ==========================================
# 🧠 SMART MODEL SELECTOR
# ==========================================
def get_working_model():
    """
    Tries models in order of preference until one works.
    """
    # Preference List: Flash (Fast) -> Pro 1.5 (Strong) -> Pro 1.0 (Legacy/Universal)
    candidates = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"]
    
    # We just return the first one for now, but the generation logic will try to fallback
    return candidates

# ==========================================
# 🖥️ UI & LOGIC
# ==========================================
with st.sidebar:
    st.title("⚖️ Contract AI")
    st.caption("v17.0 (Model Hunter)")
    
    if API_KEY:
        st.success("✅ API Key Found")
        genai.configure(api_key=API_KEY)
        
        # DIAGNOSTIC: List actually available models
        if st.checkbox("Show Available Models"):
            try:
                st.write("🔍 **Your API Key can access:**")
                for m in genai.list_models():
                    if 'generateContent' in m.supported_generation_methods:
                        st.code(m.name)
            except Exception as e:
                st.error(f"List Error: {e}")
    else:
        st.error("❌ API Key Missing")
        
    uploaded_file = st.file_uploader("Upload Contract (PDF)", type=["pdf"])

# MAIN APP
st.header("AI Contract Reviewer")

if uploaded_file and st.button("Analyze Contract"):
    if not API_KEY:
        st.error("CRITICAL: API Key is missing.")
        st.stop()

    # -- STEP A: READ PDF (Safe Mode) --
    text = ""
    with st.spinner("📄 Reading PDF..."):
        try:
            pdf_file = io.BytesIO(uploaded_file.getvalue())
            reader = PyPDF2.PdfReader(pdf_file)
            # Limit to first 20 pages to prevent token overflow
            for i in range(min(len(reader.pages), 20)):
                page_text = reader.pages[i].extract_text()
                if page_text: text += page_text + "\n"
        except Exception as e:
            st.error(f"PDF Error: {e}")
            st.stop()

    # -- STEP B: ANALYZE WITH FALLBACK --
    with st.spinner("🧠 Analyzing Risks (Auto-Switching Models)..."):
        
        prompt = """
        ACT AS A LAWYER. Review this contract text.
        Output strict JSON with these fields:
        {
            "summary": "3 bullet points",
            "risk_score": "0-100",
            "key_risks": [{"area": "string", "finding": "string"}]
        }
        
        CONTRACT TEXT:
        """ + text[:30000] # Safe char limit

        success = False
        last_error = ""
        
        # TRY MODELS IN ORDER
        model_list = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"]
        
        for model_name in model_list:
            try:
                # st.write(f"Trying model: `{model_name}`...") # Uncomment for debug
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
                
                if response.text:
                    data = json.loads(response.text)
                    
                    # RENDER RESULTS
                    st.success(f"Analysis Complete (Used Engine: {model_name})")
                    st.metric("Risk Score", f"{data.get('risk_score')}/100")
                    st.write("### Executive Summary")
                    st.markdown(data.get('summary'))
                    
                    st.write("### Key Risks")
                    for risk in data.get('key_risks', []):
                        st.error(f"**{risk.get('area')}**: {risk.get('finding')}")
                    
                    success = True
                    break # Stop if it works!
                    
            except Exception as e:
                last_error = str(e)
                continue # Try next model
        
        if not success:
            st.error("❌ All AI Models Failed.")
            st.write("Last Error:", last_error)
            st.info("Tip: Check the 'Show Available Models' box in the sidebar to see what your key supports.")
