"""
Vector service – Supabase pgvector backend, async batching, retry, rich metadata
"""
import os, asyncio, logging, hashlib
from typing import List, Dict, Any, Optional

from tenacity import retry, wait_exponential, stop_after_attempt
from openai import OpenAI

from db.supabase import get_supabase_client, safe_supabase_operation
from config.settings import OPENAI_API_KEY

# ── constants ─────────────────────────────────────────────────────────
EMBED_MODEL  = "text-embedding-3-small"   # 1536-d
EMBED_DIM    = 1536
BATCH_SIZE   = 100

logger = logging.getLogger("vector_service")

# ── Lazy initialization variables ──────────────────────────────────────
_openai_client = None

def get_openai_client():
    """Get OpenAI client with lazy initialization."""
    global _openai_client
    if _openai_client is None:
        api_key = OPENAI_API_KEY
        if not api_key:
            raise ValueError("CSA_OPENAI environment variable not set")
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client

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
def _upsert_batch(rows: List[Dict[str, Any]]):
    supabase = get_supabase_client()
    return supabase.table("documents").upsert(rows, on_conflict="id").execute()

# ── Public helpers ────────────────────────────────────────────────────
async def store_documents(
    chunks: List[str],
    namespace: str,
    source_id: str,
    category: str,
    doc_type: str = "benefit"
):
    """Batch-upsert text chunks with rich metadata into Supabase."""
    batch = []
    for i, chunk in enumerate(chunks):
        vec = await embed_text(chunk)
        vid = f"{hashlib.md5((source_id + str(i)).encode()).hexdigest()}"
        batch.append({
            "id": vid,
            "embedding": vec,
            "text": chunk,
            "source": source_id,
            "category": category,
            "type": doc_type,
            "namespace": namespace
        })
        if len(batch) >= BATCH_SIZE:
            await safe_supabase_operation(lambda: _upsert_batch(batch), "Upsert documents failed")
            batch.clear()
    if batch:
        await safe_supabase_operation(lambda: _upsert_batch(batch), "Upsert documents failed")
    logger.info("Upserted %s vectors in '%s'", len(chunks), namespace)

async def query_supabase_vector(
    query: str,
    namespace: str = "",
    filters: Optional[Dict[str, Any]] = None,
    top_k: int = 5
) -> List[Dict[str, Any]]:
    """Returns list of matches with metadata via Supabase RPC."""
    vec = await embed_text(query)
    supabase = get_supabase_client()
    payload = {
        "query_embedding": vec,
        "match_count": top_k,
        "ns": namespace or None,
        "filter": filters or {}
    }
    resp = await safe_supabase_operation(
        lambda: supabase.rpc("match_documents", payload).execute(),
        "match_documents RPC failed"
    )
    rows = resp.data or []
    return [
        {
            "text": r.get("text"),
            "source": r.get("source"),
            "category": r.get("category"),
            "type": r.get("type"),
            "score": r.get("similarity")
        }
        for r in rows
    ]


