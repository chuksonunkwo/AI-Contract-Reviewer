import streamlit as st
import os
import traceback

# ==========================================
# 🛡️ CRASH PROTECTION (The Safety Net)
# ==========================================
# We wrap the entire app in a Try/Except block.
# If ANYTHING fails, it shows the error on screen instead of crashing the server.

try:
    # 1. IMPORTS
    import google.generativeai as genai
    from fpdf import FPDF
    import PyPDF2
    import io
    import json
    import time
    from google.api_core import exceptions

    # 2. CONFIG
    st.set_page_config(page_title="Contract AI", page_icon="⚖️")
    ACTIVE_MODEL = "gemini-1.5-flash"

    # 3. API KEY
    try:
        API_KEY = os.environ.get("GEMINI_API_KEY")
        if not API_KEY:
            API_KEY = st.secrets["GEMINI_API_KEY"]
    except:
        API_KEY = None

    # 4. SIDEBAR
    with st.sidebar:
        st.title("⚖️ Contract AI")
        st.caption("v16.0 (Universal Fix)")
        
        if API_KEY:
            st.success("✅ System Online")
        else:
            st.error("❌ API Key Missing")
            st.info("Add GEMINI_API_KEY to Render Environment Variables")
            
        uploaded_file = st.file_uploader("Upload Contract (PDF)", type=["pdf"])

    # 5. MAIN LOGIC
    st.header("AI Contract Reviewer")
    
    if uploaded_file and st.button("Analyze Contract"):
        if not API_KEY:
            st.error("CRITICAL: API Key is missing.")
            st.stop()

        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel(ACTIVE_MODEL)

        # -- STEP A: READ PDF --
        with st.spinner("📄 Reading PDF..."):
            try:
                pdf_file = io.BytesIO(uploaded_file.getvalue())
                reader = PyPDF2.PdfReader(pdf_file)
                text = ""
                # Read max 50 pages to stay safe
                for i in range(min(len(reader.pages), 50)):
                    text += reader.pages[i].extract_text() + "\n"
            except Exception as e:
                st.error(f"PDF Error: {e}")
                st.stop()

        # -- STEP B: ANALYZE --
        with st.spinner("🧠 Analyzing Risks..."):
            prompt = """
            ACT AS A LAWYER. Review this contract text.
            Output strict JSON with these fields:
            {
                "summary": "3 bullet points",
                "risk_score": "0-100",
                "key_risks": [{"area": "string", "finding": "string"}]
            }
            
            CONTRACT TEXT:
            """ + text[:50000] # Safe limit

            try:
                response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
                if response.text:
                    data = json.loads(response.text)
                    
                    # RENDER RESULTS
                    st.success("Analysis Complete")
                    st.metric("Risk Score", f"{data.get('risk_score')}/100")
                    st.write("### Executive Summary")
                    st.markdown(data.get('summary'))
                    
                    st.write("### Key Risks")
                    for risk in data.get('key_risks', []):
                        st.error(f"**{risk.get('area')}**: {risk.get('finding')}")
                else:
                    st.error("AI returned empty response.")
            except Exception as e:
                st.error(f"AI Connection Error: {e}")

except Exception as main_error:
    # THIS IS THE CATCH-ALL
    st.title("⚠️ Application Error")
    st.error("The app encountered a problem, but here is the exact reason:")
    st.code(traceback.format_exc())
    st.info("Please copy the error above and share it so we can fix it.")
