"""Local RAG retrieval over the knowledge base.

Uses an in-process Chroma persistent store with a local sentence-transformers
embedding model (all-MiniLM-L6-v2, no API key). The model and Chroma client are
loaded lazily so importing this module is cheap and side-effect free.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import chromadb
from chromadb.utils import embedding_functions

_HERE = os.path.dirname(os.path.abspath(__file__))
CHROMA_DIR = os.getenv("CHROMA_DIR", os.path.join(_HERE, "chroma_db"))
DOCS_DIR = os.path.join(_HERE, "docs")
COLLECTION_NAME = "kb_docs"
EMBED_MODEL = os.getenv("EMBED_MODEL", "all-MiniLM-L6-v2")


@lru_cache(maxsize=1)
def _embedding_function():
    # Lazily constructs (and on first use downloads/loads) the local model.
    return embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)


@lru_cache(maxsize=1)
def _client():
    return chromadb.PersistentClient(path=CHROMA_DIR)


def get_collection(create: bool = False):
    """Return the Chroma collection, using the shared embedding function.

    Passing the embedding function here (for both indexing and querying) keeps
    the vector space consistent across processes.
    """
    client = _client()
    if create:
        return client.get_or_create_collection(
            name=COLLECTION_NAME, embedding_function=_embedding_function()
        )
    return client.get_collection(name=COLLECTION_NAME, embedding_function=_embedding_function())


def is_indexed() -> bool:
    try:
        return get_collection().count() > 0
    except Exception:
        return False


def search(query: str, k: int = 3) -> list[dict[str, Any]]:
    """Embed the query and return the top-k matching chunks.

    Each result: {"source": <doc filename>, "text": <chunk>, "distance": float}.
    Returns [] if nothing is indexed yet.
    """
    if not is_indexed():
        return []
    col = get_collection()
    res = col.query(query_texts=[query], n_results=k)
    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    dists = res.get("distances", [[]])[0]
    out = []
    for text, meta, dist in zip(docs, metas, dists):
        out.append(
            {
                "source": (meta or {}).get("source", "unknown"),
                "text": text,
                "distance": round(float(dist), 4),
            }
        )
    return out
