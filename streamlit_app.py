import os
import time
from pathlib import Path



import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="RAG Ingest PDF", page_icon="📄", layout="centered")


def _send_event(event_name: str, data: dict) -> str:
    event_key = os.getenv("INNGEST_EVENT_KEY", "")
    if event_key:
        url = f"https://inn.gs/e/{event_key}"
    else:
        url = "http://127.0.0.1:8288/e/test"
    resp = requests.post(url, json={"name": event_name, "data": data}, timeout=15)
    resp.raise_for_status()
    return resp.json()["ids"][0]


def save_uploaded_pdf(file) -> Path:
    uploads_dir = Path("uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    file_path = uploads_dir / file.name
    file_path.write_bytes(file.getbuffer())
    return file_path


def _backend_url() -> str:
    return os.getenv("BACKEND_URL", "http://localhost:8000")


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
    with st.spinner("Uploading and triggering ingestion..."):
        path = save_uploaded_pdf(uploaded)
        _send_event("rag/ingest_pdf", {
            "pdf_path": str(path.resolve()),
            "source_id": path.name,
        })
        time.sleep(0.3)
    st.success(f"Triggered ingestion for: {path.name}")
    st.caption("You can upload another PDF if you like.")

st.divider()
st.title("Ask a question about your PDFs")

with st.form("rag_query_form"):
    question = st.text_input("Your question")
    top_k = st.number_input("How many chunks to retrieve", min_value=1, max_value=20, value=5, step=1)
    submitted = st.form_submit_button("Ask")

    if submitted and question.strip():
        with st.spinner("Searching and generating answer..."):
            output = query_rag(question.strip(), int(top_k))
            answer = output.get("answer", "")
            sources = output.get("sources", [])

        st.subheader("Answer")
        st.write(answer or "(No answer)")
        if sources:
            st.caption("Sources")
            for s in sources:
                st.write(f"- {s}")
