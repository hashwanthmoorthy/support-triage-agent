"""One-time indexing of the knowledge base into Chroma.

Chunks each doc in knowledge_base/docs/*.txt, embeds the chunks with the local
sentence-transformers model, and upserts them into the persistent Chroma
collection. Idempotent: skips work if the collection is already populated unless
--rebuild is passed.

Run (from backend/):
    ./.venv/Scripts/python.exe -m knowledge_base.index            # index if empty
    ./.venv/Scripts/python.exe -m knowledge_base.index --rebuild  # force reindex
"""
from __future__ import annotations

import argparse
import glob
import os

from .retriever import COLLECTION_NAME, DOCS_DIR, _client, get_collection, is_indexed

# Small docs -> chunk by paragraph, splitting any long paragraph into windows.
MAX_CHARS = 400
OVERLAP = 60


MIN_CHARS = 80  # merge shorter fragments (e.g. a lone "Title:" line) forward


def _chunk(text: str) -> list[str]:
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    carry = ""  # holds a too-short fragment to prepend to the next paragraph
    for para in paras:
        if carry:
            para = carry + "\n" + para
            carry = ""
        if len(para) < MIN_CHARS:
            carry = para  # defer until we can attach real content
            continue
        if len(para) <= MAX_CHARS:
            chunks.append(para)
        else:
            start = 0
            while start < len(para):
                chunks.append(para[start : start + MAX_CHARS])
                start += MAX_CHARS - OVERLAP
    if carry:  # trailing fragment: attach to last chunk, or stand alone
        if chunks:
            chunks[-1] = chunks[-1] + "\n" + carry
        else:
            chunks.append(carry)
    return chunks


def _load_docs() -> list[tuple[str, str]]:
    paths = sorted(glob.glob(os.path.join(DOCS_DIR, "*.txt")))
    docs = []
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            docs.append((os.path.basename(path), fh.read()))
    return docs


def build_index(rebuild: bool = False) -> dict:
    if rebuild:
        try:
            _client().delete_collection(COLLECTION_NAME)
            print(f"Dropped existing collection '{COLLECTION_NAME}'.")
        except Exception:
            pass
    elif is_indexed():
        col = get_collection()
        print(f"Already indexed ({col.count()} chunks). Use --rebuild to force.")
        return {"skipped": True, "chunks": col.count()}

    col = get_collection(create=True)
    docs = _load_docs()
    if not docs:
        raise SystemExit(f"No .txt docs found in {DOCS_DIR}")

    ids, texts, metas = [], [], []
    for source, content in docs:
        for i, chunk in enumerate(_chunk(content)):
            ids.append(f"{source}::{i}")
            texts.append(chunk)
            metas.append({"source": source})

    # add() triggers embedding via the collection's embedding function.
    col.add(ids=ids, documents=texts, metadatas=metas)
    print(f"Indexed {len(docs)} docs into {len(ids)} chunks.")
    return {"skipped": False, "docs": len(docs), "chunks": len(ids)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true", help="drop and rebuild the index")
    args = ap.parse_args()
    build_index(rebuild=args.rebuild)
