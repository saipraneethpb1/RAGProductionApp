import os
import time

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="RAG PDF App", page_icon="📄", layout="centered")


def _backend_url() -> str:
    return os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")


def _wake_backend():
    """Wait for the backend to respond with 200 — handles Render free-tier cold starts (~60s)."""
    url = f"{_backend_url()}/health"
    for _ in range(48):              # up to 4 minutes
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                return
        except requests.exceptions.RequestException:
            pass
        time.sleep(5)
    raise TimeoutError("Backend is taking too long to wake up. Please try again in a minute.")


def ingest_pdf(file_bytes: bytes, filename: str) -> dict:
    resp = requests.post(
        f"{_backend_url()}/ingest",
        files={"file": (filename, file_bytes, "application/pdf")},
        timeout=180,
    )
    resp.raise_for_status()
    return resp.json()


def query_rag(question: str, top_k: int) -> dict:
    resp = requests.post(
        f"{_backend_url()}/query",
        json={"question": question, "top_k": top_k},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


st.title("Upload a PDF to Ingest")
uploaded = st.file_uploader("Choose a PDF", type=["pdf"], accept_multiple_files=False)

if uploaded is not None:
    st.info("⏳ First request may take up to 60s while the backend wakes up on Render's free tier.")
    with st.spinner("Waking up backend..."):
        _wake_backend()
    with st.spinner("Ingesting PDF — chunking, embedding, storing..."):
        result = ingest_pdf(uploaded.getvalue(), uploaded.name)
    st.success(f"Ingested {result['ingested']} chunks from: {result['source']}")
    st.caption("You can upload another PDF if you like.")

st.divider()
st.title("Ask a question about your PDFs")

with st.form("rag_query_form"):
    question = st.text_input("Your question")
    top_k = st.number_input("How many chunks to retrieve", min_value=1, max_value=20, value=5, step=1)
    submitted = st.form_submit_button("Ask")

    if submitted and question.strip():
        with st.spinner("Waking up backend if needed..."):
            _wake_backend()
            output = query_rag(question.strip(), int(top_k))
            answer = output.get("answer", "")
            sources = output.get("sources", [])

        st.subheader("Answer")
        st.write(answer or "(No answer)")
        if sources:
            st.caption("Sources")
            for s in sources:
                st.write(f"- {s}")
