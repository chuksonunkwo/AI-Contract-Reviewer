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
    st.info("Please update requirements.txt on Render to include: streamlit, google-generativeai, fpdf, PyPDF2")
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
# 🧠 DYNAMIC MODEL LOADER
# ==========================================
def get_available_models(api_key):
    """
    Asks Google which models are actually available for this Key.
    """
    try:
        genai.configure(api_key=api_key)
        models = []
        for m in genai.list_models():
            # We only want models that can generate text (not image/embedding models)
            if 'generateContent' in m.supported_generation_methods:
                # Filter for "Pro" or "Flash" or "Gemini" models only to keep list clean
                if "gemini" in m.name:
                    models.append(m.name)
        return models
    except Exception as e:
        return []

# ==========================================
# 🖥️ UI & LOGIC
# ==========================================
with st.sidebar:
    st.title("⚖️ Contract AI")
    st.caption("v18.0 (Universal Discovery)")
    
    if API_KEY:
        st.success("✅ API Key Detected")
        
        # --- THE FIX: AUTO-DISCOVERY ---
        with st.spinner("🔄 Finding available models..."):
            available_models = get_available_models(API_KEY)
        
        if available_models:
            # Sort to prefer "1.5" models first
            available_models.sort(key=lambda x: "1.5" in x, reverse=True)
            
            # Allow user to pick, but default to the best one
            selected_model = st.selectbox(
                "🤖 Active AI Model", 
                available_models,
                index=0
            )
            st.caption(f"Using: `{selected_model}`")
        else:
            st.error("❌ No Models Found. Your API Key might be invalid or restricted.")
            selected_model = None
            
    else:
        st.error("❌ API Key Missing")
        selected_model = None
        
    st.markdown("---")
    uploaded_file = st.file_uploader("Upload Contract (PDF)", type=["pdf"])

# MAIN APP
st.header("AI Contract Reviewer")

if uploaded_file and st.button("Analyze Contract"):
    if not API_KEY or not selected_model:
        st.error("CRITICAL: System not ready (Missing Key or Model).")
        st.stop()

    genai.configure(api_key=API_KEY)
    
    # -- STEP A: READ PDF (Safe Mode) --
    text = ""
    with st.spinner("📄 Reading PDF..."):
        try:
            pdf_file = io.BytesIO(uploaded_file.getvalue())
            reader = PyPDF2.PdfReader(pdf_file)
            # Limit to first 30 pages to prevent token overflow
            for i in range(min(len(reader.pages), 30)):
                page_text = reader.pages[i].extract_text()
                if page_text: text += page_text + "\n"
        except Exception as e:
            st.error(f"PDF Error: {e}")
            st.stop()

    # -- STEP B: ANALYZE --
    with st.spinner(f"🧠 Analyzing with {selected_model}..."):
        
        prompt = """
        ACT AS A LAWYER. Review this contract text.
        Output strict JSON with these fields:
        {
            "summary": "3 bullet points",
            "risk_score": "0-100",
            "key_risks": [{"area": "string", "finding": "string"}]
        }
        
        CONTRACT TEXT:
        """ + text[:40000] # Safe char limit

        try:
            # Use the model selected from the dropdown
            model = genai.GenerativeModel(selected_model)
            response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
            
            if response.text:
                try:
                    data = json.loads(response.text)
                    
                    # RENDER RESULTS
                    st.success("Analysis Complete")
                    
                    c1, c2 = st.columns(2)
                    c1.metric("Risk Score", f"{data.get('risk_score')}/100")
                    c2.metric("Engine", selected_model.split("/")[-1])
                    
                    st.write("### Executive Summary")
                    st.markdown(data.get('summary'))
                    
                    st.write("### Key Risks")
                    for risk in data.get('key_risks', []):
                        st.error(f"**{risk.get('area')}**: {risk.get('finding')}")
                except json.JSONDecodeError:
                    st.warning("Raw Output (JSON Parse Failed):")
                    st.write(response.text)
            else:
                st.error("AI returned empty response.")
                
        except Exception as e:
            st.error(f"Analysis Failed: {e}")
            st.info("👉 Try selecting a different model in the sidebar!")
