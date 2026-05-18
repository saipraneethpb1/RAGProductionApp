# RAG Production App

A production-grade Retrieval-Augmented Generation (RAG) application built with Inngest workflow orchestration, Qdrant vector search, FastEmbed embeddings, and Groq LLM.

## 🚀 Live Demo

**[https://ragappuctionapp-axmgpfaxbgwaxbqbkhfpot.streamlit.app/](https://ragappuctionapp-axmgpfaxbgwaxbqbkhfpot.streamlit.app/)**

## Tech Stack

- **LLM** — Groq (`llama-3.1-8b-instant`) — free, fast inference
- **Embeddings** — FastEmbed (`BAAI/bge-small-en-v1.5`) — local ONNX, no API key needed
- **Vector DB** — Qdrant Cloud — free 1 GB cluster
- **Workflow** — Inngest — event-driven, durable function execution with retries, throttling, and rate limiting
- **Backend** — FastAPI + Uvicorn deployed on Render
- **Frontend** — Streamlit deployed on Streamlit Cloud

## Architecture

```
Streamlit UI  →  Inngest Cloud  →  FastAPI Worker  →  Qdrant Cloud
                                        ↓
                                   FastEmbed + Groq
```

1. **Ingest**: Upload a PDF → Inngest triggers the ingest function → PDF is chunked, embedded, and stored in Qdrant
2. **Query**: Ask a question → Inngest triggers the query function → question is embedded, top-k chunks retrieved, Groq generates the answer

## Features

- Throttled PDF ingestion (2 per minute, 1 per source per 4 hours)
- Durable multi-step Inngest functions with automatic retries
- Module-level Qdrant connection singleton for efficient reuse
- Deduplication of chunk IDs using UUID5

## Local Development

### Prerequisites
- Docker (for Qdrant)
- Node.js (for Inngest Dev Server)

### Setup

```bash
# Clone the repo
git clone https://github.com/saipraneethpb1/RAGProductionApp.git
cd RAGProductionApp

# Install dependencies
pip install -e .

# Copy env template and fill in your keys
cp .env.example .env
```

### Running locally (4 terminals)

```bash
# Terminal 1 — Qdrant
docker run -p 6333:6333 qdrant/qdrant

# Terminal 2 — FastAPI backend
uvicorn main:app --reload --port 8000

# Terminal 3 — Inngest Dev Server
npx inngest-cli@latest dev -u http://localhost:8000/api/inngest

# Terminal 4 — Streamlit UI
streamlit run streamlit_app.py
```

Open **http://localhost:8501** in your browser.

## Environment Variables

See `.env.example` for all required variables.

| Variable | Description |
|----------|-------------|
| `GROQ_API_KEY` | Free at [console.groq.com](https://console.groq.com) |
| `QDRANT_URL` | Cluster URL from [cloud.qdrant.io](https://cloud.qdrant.io) |
| `QDRANT_API_KEY` | API key from Qdrant Cloud dashboard |
| `INNGEST_SIGNING_KEY` | From [app.inngest.com](https://app.inngest.com) Settings |
| `INNGEST_EVENT_KEY` | From [app.inngest.com](https://app.inngest.com) Settings |
| `INNGEST_API_BASE` | Set to `https://api.inngest.com/v1` for cloud |
