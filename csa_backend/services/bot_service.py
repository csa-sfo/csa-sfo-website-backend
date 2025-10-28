from fastapi import FastAPI, Request
from openai import OpenAI
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
# from config.settings import PINECONE_API_KEY, OPENAI_API_KEY
from knowledge_base.website_content import scrapped_website_content,get_urls
from knowledge_base.sales_content import get_sales_content
import logging
import os
import json
import hashlib
from pydantic import BaseModel
import time
from services.supabase_vector_service import store_documents, get_openai_client, query_supabase_vector, store_prepared_documents
from db.supabase import get_supabase_client, safe_supabase_operation

app = FastAPI()


OPENAI_API_KEY = os.getenv("CSA_OPENAI")

# openai_client = OpenAI(api_key=OPENAI_API_KEY)
# Vector store is Supabase; no index bootstrap here

hashes = {}


# OpenAI client is initialized lazily
# No need to redefine these functions

# Split content into smaller chunks
async def split_content(content, chunk_size=500):
    if not content:
        logging.warning("No content to split")
        return []
    words = content.split()
    final_chunks = []
    current_chunk = []
    current_length = 0
    for word in words:
        word_length = len(word) + 1
        if current_length + word_length > chunk_size and current_chunk:
            final_chunks.append(" ".join(current_chunk))
            current_chunk = [word]
            current_length = word_length
        else:
            current_chunk.append(word)
            current_length += word_length
    if current_chunk:
        final_chunks.append(" ".join(current_chunk))
    logging.info(f"Split content into {len(final_chunks)} chunks")
    return [chunk.strip() for chunk in final_chunks if chunk.strip()]

# Create embeddings using OpenAI
async def create_embedding(text):
    # Delegate to supabase_vector_service embed with retries
    from services.supabase_vector_service import embed_text
    return await embed_text(text)


# Compute hash of content
def compute_hash(content):
    """Compute a SHA-256 hash of the content."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

# Load hashes from file
def load_hashes():
    """Load stored hashes from hashes.json."""
    if os.path.exists('hashes.json'):
        with open('hashes.json', 'r') as f:
            logging.info("Loading hashes from file")
            return json.load(f)
    logging.info("No hashes file found, starting with empty hashes")
    return {}

# Save hashes to file
def save_hashes():
    """Save the current hashes to hashes.json."""
    with open('hashes.json', 'w') as f:
        json.dump(hashes, f)

async def store_embeddings(chunks: list[str], namespace: str, source_id: str):
    """Deprecated: use store_documents from services.pinecone_service."""
    await store_documents(chunks, namespace, source_id, category="Website")


def split_overlap(text: str, size: int = 400, overlap: int = 50):
    words = text.split()
    for start in range(0, len(words), size - overlap):
        yield " ".join(words[start:start + size])


# Website content initialization
async def initialize_website_content():
    urls = get_urls()
    for url in urls:
        content = await scrapped_website_content(url)
        chunks  = list(split_overlap(content))
        await store_documents(
                chunks=chunks,
                namespace="website",
                source_id=url,
                category="Website"
            )
        hashes[url] = compute_hash(content)
    save_hashes()

#  Sales content initialization
async def initialize_sales_content():
    sales_items = await get_sales_content()
    for item in sales_items:
        chunks = list(split_overlap(item["content"]))
        await store_documents(
            chunks=chunks,
            namespace="sales",
            source_id=item["title"],
            category=item["title"],   # e.g., Cloud Engineering
            doc_type="benefit"
        )

def check_index_stats():
    supabase = get_supabase_client()
    def count_ns(ns: str):
        resp = supabase.table("documents").select("id", count="exact").eq("namespace", ns).execute()
        return resp.count or 0
    try:
        website = count_ns("website")
        sales   = count_ns("sales")
        total   = (website or 0) + (sales or 0)
        logging.info(f"Vector store stats (website={website}, sales={sales}, total={total})")
        return {"namespaces": {"website": {"vector_count": website}, "sales": {"vector_count": sales}}, "total_vector_count": total}
    except Exception as e:
        logging.warning(f"Failed to get vector stats: {e}")
        return {"namespaces": {}, "total_vector_count": 0}

# Refresh embeddings for a single URL
async def refresh_url(url: str, content: str | None = None):
    """Refresh Pinecone embeddings for a given URL.

    Args:
        url (str): The page URL.
        content (str | None): Pre-fetched page content. If ``None`` the URL will be scraped internally.
    """
    # Fetch latest content if not provided
    if content is None:
        content = await scrapped_website_content(url)

    # Guard against empty scrape results
    if not content:
        logging.warning(f"No content found for {url}. Skipping refresh.")
        return

    # ----- Chunk + embed -----
    try:
        chunks: list[str] = await split_content(content)
    except TypeError:
        # Fallback if split_content still returns coroutine when forgotten to await elsewhere
        chunks = await split_content(content)

    if not chunks:
        logging.warning(f"No chunks generated for {url}. Skipping refresh.")
        return

    # Delete existing vectors for this URL in Supabase
    supabase = get_supabase_client()
    await safe_supabase_operation(lambda: supabase.table("documents").delete().eq("source", url).execute(), "Delete by source failed")

    # Upsert new vectors via store_documents
    await store_documents(chunks=chunks, namespace="website", source_id=url, category="Website")
    
    # Update hash
    hash_value = compute_hash(content)
    hashes[url] = hash_value
    save_hashes()

# Check for updates periodically
async def check_for_updates():
    """Periodically check for content changes and refresh embeddings."""
    urls = get_urls()
    for url in urls:
        try:
            content = await scrapped_website_content(url)
            new_hash = compute_hash(content)
            if new_hash != hashes.get(url):
                logging.info(f"Change detected for {url}, refreshing...")
                await refresh_url(url, content)
            else:
                logging.info(f"No change for {url}")
        except Exception as e:
            logging.error(f"Failed to check {url}: {e}")

# Refresh multiple URLs
async def refresh_urls(urls_to_refresh: list[str]):
    for url in urls_to_refresh:
        logging.info(f"Refreshing {url}")
        await refresh_url(url)
        logging.info(f"Finished refreshing {url}")

# Pydantic model for refresh request
class RefreshRequest(BaseModel):
    refresh_urls: list[str] = []

# Retrieve relevant chunks from Supabase
async def retrieve_relevant_chunks(query, top_k=5):
    matches = await query_supabase_vector(query, top_k=top_k)
    return [m["text"] for m in matches]

# def export_supabase_vector_to_markdown(output_file="supabase_vector_content.md"):
#     try:
#         index = get_pinecone_index()
#         stats = index.describe_index_stats()
#         logging.info(f"Exporting Pinecone data (vectors: {stats.get('total_vector_count', 'N/A')})")

#         all_texts_by_url = {}

#         # You'll need to paginate through all items in Pinecone (simulate with a dummy vector if needed)
#         dummy_vector = [0.0] * stats['dimension']
#         results = index.query(
#             vector=dummy_vector,
#             top_k=10000,
#             include_metadata=True
#         )

#         for match in results.get("matches", []):
#             metadata = match.get("metadata", {})
#             text = metadata.get("text", "")
#             url = metadata.get("url", "unknown-url")
#             if url not in all_texts_by_url:
#                 all_texts_by_url[url] = []
#             all_texts_by_url[url].append(text)

#         # Write to markdown
#         with open(output_file, "w", encoding="utf-8") as f:
#             for url, chunks in all_texts_by_url.items():
#                 f.write(f"# Content from: {url}\n\n")
#                 for chunk in chunks:
#                     f.write(f"{chunk}\n\n---\n\n")
#         logging.info(f"Markdown file '{output_file}' created successfully.")

#     except Exception as e:
#         logging.error(f"Failed to export Pinecone data to markdown: {e}")
def export_supabase_vector_to_markdown(output_file="supabase_vector_content.md"):
    try:
        supabase = get_supabase_client()
        resp = supabase.table("documents").select("source,text").execute()
        rows = resp.data or []
        all_texts_by_url = {}
        for r in rows:
            url = r.get("source") or "unknown-url"
            text = r.get("text") or ""
            if url and text:
                all_texts_by_url.setdefault(url, []).append(text)

        # Write to markdown
        with open(output_file, "w", encoding="utf-8") as f:
            for url, chunks in all_texts_by_url.items():
                f.write(f"# Content from: {url}\n\n")
                for chunk in chunks:
                    f.write(f"{chunk}\n\n---\n\n")

        logging.info(f"Markdown file '{output_file}' created successfully.")
    except Exception as e:
        logging.exception(f"Failed to export Pinecone content: {e}")

def delete_all_supabase_vector_data():
    """
    Deletes all vectors from the Pinecone index.
    WARNING: This operation is irreversible.
    """
    try:
        supabase = get_supabase_client()
        supabase.table("documents").delete().neq("id","").execute()
        logging.info("All supabase_vector vectors deleted successfully.")
    except Exception as e:
        logging.error(f"Failed to delete vectors from Pinecone: {e}")
import re

def convert_markdown_links_to_html(text):
    pattern = r"\[([^\]]+)\]\(([^)]+)\)"
    return re.sub(pattern, r'<a href="\2" target="_blank" style="color: blue; text-decoration: underline;">\1</a>', text)

   

# Events content initialization via Supabase RPC
async def initialize_events_content(chunk_size: int = 400, overlap: int = 50) -> int:
    """Fetch pre-chunked event rows via RPC and store with embeddings into documents.

    Returns number of vectors upserted.
    """
    supabase = get_supabase_client()
    payload = {"chunk_size": chunk_size, "overlap": overlap}
    resp = await safe_supabase_operation(
        lambda: supabase.rpc("prepare_event_documents", payload).execute(),
        "prepare_event_documents RPC failed",
    )
    rows = resp.data or []
    if not rows:
        logging.info("No event rows returned from prepare_event_documents")
        return 0
    upserted = await store_prepared_documents(rows)
    logging.info(f"Initialized events content: upserted {upserted} vectors")
    return upserted


async def initialize_site_and_events():
    """Convenience wrapper: initialize website and events content."""
    await initialize_website_content()
    await initialize_events_content()
