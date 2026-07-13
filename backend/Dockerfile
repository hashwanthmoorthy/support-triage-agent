# Backend image: FastAPI app + LangGraph agent + MCP server + local RAG.
# One image is used for BOTH the `backend` (uvicorn) and `mcp` (MCP server)
# compose services — the command is overridden per service.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    # Bake the HF model cache into a fixed in-image location.
    HF_HOME=/app/hf_cache

WORKDIR /app

# Install CPU-only torch first so we don't pull the multi-GB CUDA wheel that
# sentence-transformers would otherwise drag in (keeps the image t3.micro-sized).
# Then the rest of the pinned deps (torch is already satisfied).
COPY requirements.txt .
RUN pip install torch==2.13.0 --index-url https://download.pytorch.org/whl/cpu \
 && pip install -r requirements.txt

COPY . .

# Bake the embedding model + pre-built Chroma index INTO the image at build time
# (no API key needed — embeddings are local). This step needs network access to
# download the model from Hugging Face.
RUN python -m knowledge_base.index

# From here on, force Hugging Face fully offline so the RUNTIME never contacts
# huggingface.co (not even revision HEAD checks) — it loads the baked cache
# only. Set AFTER the download step above so the build can still fetch.
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

EXPOSE 8000 8100

# Default command (the `backend` service). The `mcp` service overrides this.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
