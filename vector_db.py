import os
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct

from data_loader import EMBED_DIM


class QdrantStorage:
    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        collection: str = "docs",
        dim: int = EMBED_DIM,
    ):
        url = url or os.getenv("QDRANT_URL", "http://localhost:6333")
        api_key = api_key or os.getenv("QDRANT_API_KEY") or None
        self.client = QdrantClient(url=url, api_key=api_key, timeout=30)
        self.collection = collection
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )

    def upsert(self, ids, vectors, payloads):
        points = [PointStruct(id=ids[i], vector=vectors[i], payload=payloads[i]) for i in range(len(ids))]
        self.client.upsert(self.collection, points=points)

    def search(self, query_vector, top_k: int = 5):
        response = self.client.query_points(
            collection_name=self.collection,
            query=query_vector,
            with_payload=True,
            limit=top_k,
        )
        contexts = []
        sources = set()

        for r in response.points:
            payload = getattr(r, "payload", None) or {}
            text = payload.get("text", "")
            source = payload.get("source", "")
            if text:
                contexts.append(text)
                if source:
                    sources.add(source)

        return {"contexts": contexts, "sources": list(sources)}


# Module-level singleton — reuses the Qdrant connection across steps in the same process
_storage: QdrantStorage | None = None


def get_storage() -> QdrantStorage:
    global _storage
    if _storage is None:
        _storage = QdrantStorage()
    return _storage
