"""
Pinecone service – async batching, retry, rich metadata
"""
import os, asyncio, logging, hashlib
from typing import List, Dict, Any, Optional

from tenacity import retry, wait_exponential, stop_after_attempt
from openai import OpenAI

from pinecone import Pinecone, ServerlessSpec
from config.settings import PINECONE_API_KEY,OPENAI_API_KEY

# ── constants ─────────────────────────────────────────────────────────
EMBED_MODEL  = "text-embedding-3-small"   # 1536-d, 3× Ada quality
EMBED_DIM    = 1536
BATCH_SIZE   = 100

logger = logging.getLogger("pinecone_service")

# ── Lazy initialization variables ──────────────────────────────────────
_openai_client = None
_pinecone_index = None
_pinecone_client = None

def get_openai_client():
    """Get OpenAI client with lazy initialization."""
    global _openai_client
    if _openai_client is None:
        api_key = OPENAI_API_KEY
        if not api_key:
            raise ValueError("CSA_OPENAI environment variable not set")
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client

def get_pinecone_client():
    """Get Pinecone client with lazy initialization."""
    global _pinecone_client
    if _pinecone_client is None:
        api_key = PINECONE_API_KEY
        if not api_key:
            raise ValueError("CSA_PINECONE environment variable not set")
        _pinecone_client = Pinecone(api_key=api_key)
    return _pinecone_client

def get_pinecone_index():
    """Get Pinecone index with lazy initialization."""
    global _pinecone_index
    if _pinecone_index is None:
        pc = get_pinecone_client()
        INDEX_NAME = "csa-sfo-website-content"
        
        if INDEX_NAME not in pc.list_indexes().names():
            pc.create_index(
                name=INDEX_NAME,
                dimension=EMBED_DIM,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1")
            )
        _pinecone_index = pc.Index(INDEX_NAME)
    return _pinecone_index

async def embed_text(text: str) -> List[float]:
    """Returns 1536-d embedding list."""
    client = get_openai_client()
    resp = await asyncio.to_thread(
        lambda: client.embeddings.create(
            input=text,
            model=EMBED_MODEL
        )
    )
    return resp.data[0].embedding

# ── Retry wrappers for upsert / query ─────────────────────────────────
@retry(wait=wait_exponential(), stop=stop_after_attempt(5))
def _upsert_batch(vectors: List[Dict[str, Any]], namespace: str):
    index = get_pinecone_index()
    index.upsert(vectors=vectors, namespace=namespace)

@retry(wait=wait_exponential(), stop=stop_after_attempt(5))
def _query(vector: List[float], top_k: int, namespace: str, filters: Dict[str, Any]):
    index = get_pinecone_index()
    return index.query(
        vector=vector,
        top_k=top_k,
        include_metadata=True,
        namespace=namespace,
        filter=filters or {}
    )

# ── Public helpers ────────────────────────────────────────────────────
async def store_documents(
    chunks: List[str],
    namespace: str,
    source_id: str,
    category: str,
    doc_type: str = "benefit"
):
    """Batch-upsert text chunks with rich metadata."""
    batch = []
    for i, chunk in enumerate(chunks):
        vec = await embed_text(chunk)
        vid = f"{hashlib.md5((source_id + str(i)).encode()).hexdigest()}"
        batch.append({
            "id": vid,
            "values": vec,
            "metadata": {
                "text": chunk,
                "source": source_id,
                "category": category,
                "type": doc_type
            }
        })
        if len(batch) >= BATCH_SIZE:
            _upsert_batch(batch, namespace)
            batch.clear()
    if batch:
        _upsert_batch(batch, namespace)
    logger.info("Upserted %s vectors in '%s'", len(chunks), namespace)

async def query_pinecone(
    query: str,
    namespace: str = "",
    filters: Optional[Dict[str, Any]] = None,
    top_k: int = 5
) -> List[Dict[str, Any]]:
    """Returns list of matches with metadata."""
    vec = await embed_text(query)
    res = _query(vec, top_k, namespace, filters or {})
    return [
        {
            "text": m["metadata"]["text"],
            "source": m["metadata"].get("source"),
            "category": m["metadata"].get("category"),
            "type": m["metadata"].get("type"),
            "score": m["score"]
        }
        for m in res["matches"]
    ]
