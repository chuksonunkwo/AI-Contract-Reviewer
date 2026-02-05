import streamlit as st
import os

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
st.set_page_config(page_title="System Test", page_icon="🛠️")

st.title("🛠️ Bare Metal Connection Test")

# 1. CHECK API KEY
try:
    API_KEY = os.environ.get("GEMINI_API_KEY")
    if not API_KEY:
        API_KEY = st.secrets["GEMINI_API_KEY"]
    st.success(f"✅ API Key Detected: {API_KEY[:5]}...*****")
except:
    st.error("❌ API Key NOT Found. Please check your Render Environment Variables.")
    st.stop()

# 2. CHECK GOOGLE LIBRARY
try:
    import google.generativeai as genai
    st.success("✅ Google AI Library Installed")
    genai.configure(api_key=API_KEY)
except ImportError:
    st.error("❌ Google AI Library MISSING. Add `google-generativeai` to requirements.txt")
    st.stop()

# 3. TEST CONNECTION
st.write("---")
if st.button("🚀 Test Connection to Gemini 1.5 Flash"):
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        with st.spinner("Ping Google..."):
            response = model.generate_content("Reply with exactly one word: 'Operational'")
            st.success(f"✅ Google Responded: **{response.text}**")
            st.balloons()
    except Exception as e:
        st.error(f"❌ Connection Failed: {e}")
        st.info("Common fixes: Check if your API Key is active in Google AI Studio.")

st.write("---")
st.caption("If this test passes, the problem is with the PDF libraries (PyPDF2/FPDF). If this fails, the problem is your API Key or Render Setup.")
