import re

from fastembed import TextEmbedding
from pypdf import PdfReader
from dotenv import load_dotenv

load_dotenv()

EMBED_MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBED_DIM = 384

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

_embedder = TextEmbedding(EMBED_MODEL_NAME)


def split_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Sentence-aware splitter: packs sentences into ~chunk_size chars with overlap."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks: list[str] = []
    cur = ""
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        if not cur or len(cur) + len(sent) + 1 <= chunk_size:
            cur = f"{cur} {sent}".strip()
        else:
            chunks.append(cur)
            cur = (cur[-overlap:].lstrip() + " " + sent).strip()
        # hard-split anything longer than chunk_size (e.g. text without sentence breaks)
        while len(cur) > chunk_size:
            chunks.append(cur[:chunk_size])
            cur = cur[chunk_size - overlap:].lstrip()
    if cur:
        chunks.append(cur)
    return chunks


def load_and_chunk_pdf(path: str) -> list[str]:
    reader = PdfReader(path)
    chunks: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            chunks.extend(split_text(text))
    return chunks


def embed_texts(texts: list[str]) -> list[list[float]]:
    # Small batches keep peak memory under Render's 512 MB free-tier limit
    return [emb.tolist() for emb in _embedder.embed(texts, batch_size=8)]
