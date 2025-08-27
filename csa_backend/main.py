from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import asyncio
# from indra_bot import WebContentProcessor
from routes_register import router as api_router
from routers.payments import payment_router
from contextlib import asynccontextmanager
from services.bot_service import initialize_website_content, initialize_sales_content, get_pinecone_index, load_hashes, check_for_updates, get_urls, check_index_stats
# from backend.config.settings import PINECONE_API_KEY
from apscheduler.schedulers.background import BackgroundScheduler   
import logging
from fastapi.responses import Response
from services.sales_content_check import sales_content_changed
import uvicorn

from redis.asyncio import Redis
from services.cache_service import init_redis_client
from config.settings import REDIS_URL

logging.basicConfig(level=logging.INFO)

# Define lifespan manager first
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
    # ========== REDIS CACHE INITIALIZATION ==========
        # redis_url = REDIS_URL
        # #logging.info(f"Connecting to Redis at {redis_url}")
        # if not redis_url:
        #     raise ValueError("REDIS_URL is not set in the environment variables.")
        # try:
        #     redis = Redis.from_url(redis_url, decode_responses=True)
        #     init_redis_client(redis)
        # except Exception as e:
        #     logging.warning(f"Failed to connect to Redis: {e}. Continuing without Redis cache.")
        #     redis = None

    

        global hashes
        hashes = load_hashes()
        index = get_pinecone_index()
        stats = index.describe_index_stats()
        website_count = stats["namespaces"].get("website", {}).get("vector_count", 0)
        logging.info(f"Website vector count: {website_count}")
        sales_count   = stats["namespaces"].get("sales",   {}).get("vector_count", 0)
        logging.info(f"Vector count : {stats['total_vector_count']}")
        if website_count == 0:
            await initialize_website_content()
        # if sales_count == 0:
        #     await initialize_sales_content()
        # if website_count == 0 and sales_count == 0:
        #     logging.info("Initializing pinecone")
        #     await initialize_website_content()
        #     await initialize_sales_content()
        # if await sales_content_changed():
        #     logging.info("Sales content changed, refreshing...")
        #     await initialize_sales_content()
        # Periodic refresh (async)
        async def refresh_task():
            logging.info("Starting periodic refresh task...")
            while True:
                logging.info("Sleeping for 24 hours before checking for updates...")
                await asyncio.sleep(86400)  # Wait 24 hours before each check
                logging.info("Checking for updates...")
                try:
                    await check_for_updates()
                    logging.info("Update check completed successfully.")
                except Exception as e:
                    logging.error(f"Error during periodic update check: {e}") 

        loop = asyncio.get_event_loop()
        loop.create_task(refresh_task())
        yield
    except Exception as e:
        logging.error(f"Error during lifespan startup: {e}")
        raise  # Re-raise if you want the app to fail on startup errors
    finally:
        # Cleanup resources in finally block to ensure they run even on errors
        if hasattr(app.state, 'scheduler'):
            app.state.scheduler.shutdown()
        if hasattr(app.state, 'redis'):
            app.state.redis.close()     
        pass

# Create the FastAPI app once
app = FastAPI(
    title="CSA SFO Website Server",
    description="A web server for CSA SFO Website",
    version="1.0.0",
    docs_url=f"/docs",
    redirect_slashes=False,
    lifespan=lifespan
)

# Allow frontend origins
origins = [
    "https://dashboard.vapi.ai",
    "http://localhost:8081",
    "http://localhost:8080",
    "http://127.0.0.1:8081",
    "http://127.0.0.1:8080",
    "http://localhost:3000",  # React default port
    "http://127.0.0.1:3000",
    "http://localhost:5173",  # Vite default port
    "http://127.0.0.1:5173",
    "https://csasfo.com",
    "https://www.csasfo.com"
]

# Include routers
app.include_router(api_router)
app.include_router(payment_router, prefix="/api/v1")  # Add this line to include payments router

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Allows specific origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all HTTP methods (GET, POST, etc.)
    allow_headers=["*"],  # Allows all headers
)

# Custom middleware to handle OPTIONS requests
async def custom_cors_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        response = Response(status_code=200)
        origin = request.headers.get("origin")
        req_method = request.headers.get("access-control-request-method")
        req_headers = request.headers.get("access-control-request-headers")
        if origin in origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = req_method or "POST, GET, OPTIONS"
            # Reflect requested headers to satisfy strict preflights
            if req_headers:
                response.headers["Access-Control-Allow-Headers"] = req_headers
            else:
                response.headers["Access-Control-Allow-Headers"] = "content-type, authorization"
            response.headers["Access-Control-Allow-Credentials"] = "true"
        return response
    
    # Process non-OPTIONS requests normally
    response = await call_next(request)
    origin = request.headers.get("origin")
    if origin in origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Headers"] = "content-type, authorization"
    return response

# Apply the custom middleware
app.middleware("http")(custom_cors_middleware)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logging.info(f"Request: {request.method} {request.url} Origin: {request.headers.get('origin')}")
    response = await call_next(request)
    return response

# Global bot instance
# bot = WebContentProcessor()

# Flag to ensure processing runs only once
# startup_ran = False

# List of URLs to process on startup
urls = get_urls()

# Include API router
app.include_router(api_router, prefix="/v1/routes")
