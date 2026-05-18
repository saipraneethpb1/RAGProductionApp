import logging
import os
import uuid
import datetime

import tempfile
from fastapi import FastAPI, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
import inngest
import inngest.fast_api

from data_loader import load_and_chunk_pdf, embed_texts
from vector_db import get_storage
from custom_types import RAGSearchResult, RAGUpsertResult, RAGChunkAndSrc

load_dotenv()

_groq = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
)

inngest_client = inngest.Inngest(
    app_id="rag_app",
    logger=logging.getLogger("uvicorn"),
    is_production=bool(os.getenv("INNGEST_SIGNING_KEY")),
    signing_key=os.getenv("INNGEST_SIGNING_KEY"),
    serializer=inngest.PydanticSerializer(),
)


@inngest_client.create_function(
    fn_id="RAG: Ingest PDF",
    trigger=inngest.TriggerEvent(event="rag/ingest_pdf"),
    throttle=inngest.Throttle(limit=2, period=datetime.timedelta(minutes=1)),
    rate_limit=inngest.RateLimit(
        limit=1,
        period=datetime.timedelta(hours=4),
        key="event.data.source_id",
    ),
)
async def rag_ingest_pdf(ctx: inngest.Context):
    def _load(ctx: inngest.Context) -> RAGChunkAndSrc:
        pdf_path = ctx.event.data["pdf_path"]
        source_id = ctx.event.data.get("source_id", pdf_path)
        chunks = load_and_chunk_pdf(pdf_path)
        return RAGChunkAndSrc(chunks=chunks, source_id=source_id)

    def _upsert(chunks_and_src: RAGChunkAndSrc) -> RAGUpsertResult:
        chunks = chunks_and_src.chunks
        source_id = chunks_and_src.source_id
        vecs = embed_texts(chunks)
        ids = [str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source_id}:{i}")) for i in range(len(chunks))]
        payloads = [{"source": source_id, "text": chunks[i]} for i in range(len(chunks))]
        get_storage().upsert(ids, vecs, payloads)
        return RAGUpsertResult(ingested=len(chunks))

    chunks_and_src = await ctx.step.run("load-and-chunk", lambda: _load(ctx), output_type=RAGChunkAndSrc)
    ingested = await ctx.step.run("embed-and-upsert", lambda: _upsert(chunks_and_src), output_type=RAGUpsertResult)
    return ingested.model_dump()


@inngest_client.create_function(
    fn_id="RAG: Query PDF",
    trigger=inngest.TriggerEvent(event="rag/query_pdf_ai"),
)
async def rag_query_pdf_ai(ctx: inngest.Context):
    def _search(question: str, top_k: int = 5) -> RAGSearchResult:
        query_vec = embed_texts([question])[0]
        found = get_storage().search(query_vec, top_k=top_k)
        return RAGSearchResult(contexts=found["contexts"], sources=found["sources"])

    def _answer(context_block: str, question: str) -> str:
        res = _groq.chat.completions.create(
            model="llama-3.1-8b-instant",
            max_tokens=1024,
            temperature=0.2,
            messages=[
                {"role": "system", "content": "You answer questions using only the provided context."},
                {"role": "user", "content": (
                    "Use the following context to answer the question.\n\n"
                    f"Context:\n{context_block}\n\n"
                    f"Question: {question}\n"
                    "Answer concisely using the context above."
                )},
            ],
        )
        return res.choices[0].message.content.strip()

    question = ctx.event.data["question"]
    top_k = int(ctx.event.data.get("top_k", 5))

    found = await ctx.step.run("embed-and-search", lambda: _search(question, top_k), output_type=RAGSearchResult)

    context_block = "\n\n".join(f"- {c}" for c in found.contexts)
    answer = await ctx.step.run("llm-answer", lambda: _answer(context_block, question))

    return {"answer": answer, "sources": found.sources, "num_contexts": len(found.contexts)}


class QueryRequest(BaseModel):
    question: str
    top_k: int = 5


app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
inngest.fast_api.serve(app, inngest_client, [rag_ingest_pdf, rag_query_pdf_ai])


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    return JSONResponse(status_code=500, content={
        "error": type(exc).__name__,
        "detail": str(exc),
        "trace": traceback.format_exc()[-2000:],
    })


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/ingest")
async def ingest(file: UploadFile = File(...)):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        source_id = file.filename or tmp_path
        chunks = load_and_chunk_pdf(tmp_path)
        vecs = embed_texts(chunks)
        ids = [str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source_id}:{i}")) for i in range(len(chunks))]
        payloads = [{"source": source_id, "text": chunks[i]} for i in range(len(chunks))]
        get_storage().upsert(ids, vecs, payloads)
        return {"ingested": len(chunks), "source": source_id}
    finally:
        os.unlink(tmp_path)


@app.post("/query")
async def query(req: QueryRequest):
    query_vec = embed_texts([req.question])[0]
    found = get_storage().search(query_vec, top_k=req.top_k)
    context_block = "\n\n".join(f"- {c}" for c in found["contexts"])
    res = _groq.chat.completions.create(
        model="llama-3.1-8b-instant",
        max_tokens=1024,
        temperature=0.2,
        messages=[
            {"role": "system", "content": "You answer questions using only the provided context."},
            {"role": "user", "content": (
                "Use the following context to answer the question.\n\n"
                f"Context:\n{context_block}\n\n"
                f"Question: {req.question}\n"
                "Answer concisely using the context above."
            )},
        ],
    )
    return {
        "answer": res.choices[0].message.content.strip(),
        "sources": found["sources"],
        "num_contexts": len(found["contexts"]),
    }
