# =============================================================================
# backend/Dockerfile — AI Customer Support Platform Backend
# =============================================================================
# Uses CPU-only PyTorch (~250 MB) instead of the default CUDA build (~3.5 GB).
# The embedding model runs fine on CPU for this workload.
# =============================================================================

FROM python:3.11-slim

WORKDIR /app

# Install system deps required by sentence-transformers
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Step 1: Install CPU-only PyTorch FIRST.
# Without this, pip resolves torch from PyPI and downloads the full 3.5 GB
# CUDA build (cublas, cudnn, cusolver, etc.) which nobody needs here.
RUN pip install --no-cache-dir \
    torch \
    --index-url https://download.pytorch.org/whl/cpu

# Step 2: Install remaining dependencies.
# torch is already satisfied, so sentence-transformers won't pull GPU torch.
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the embedding model so container startup is instant
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
