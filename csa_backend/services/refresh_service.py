
from services.bot_service import split_content
from pydantic import BaseModel
import logging
from db.supabase import get_supabase_client
from services.supabase_vector_service import store_documents

# Refresh a single URL's embeddings
def refresh_url(url):
    supabase = get_supabase_client()
    # Caller should provide content upstream; here we only clear existing
    supabase.table("documents").delete().eq("source", url).execute()
    logging.info(f"Cleared supabase_vector vectors for {url}")

# Refresh multiple URLs
def refresh_urls(urls_to_refresh):
    for url in urls_to_refresh:
        logging.info(f"Refreshing {url}")
        refresh_url(url)
        logging.info(f"Finished refreshing {url}")

# Pydantic model for refresh request
class RefreshRequest(BaseModel):
    refresh_urls: list[str] = []