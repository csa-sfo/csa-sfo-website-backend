from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
import asyncio
import time
import logging
from datetime import datetime
from app.config_simple import settings
from contextlib import asynccontextmanager


# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Import routers with error handling
try:
    from routes_register import router as api_router
    from routers.payments import payment_router
    from routers.router import message_router
    from services.bot_service import initialize_website_content, initialize_events_content, initialize_sales_content, load_hashes, check_for_updates, get_urls, check_index_stats
except ImportError as e:
    logger.error(f"Failed to import required modules: {e}")
    # Create empty routers if imports fail
    from fastapi import APIRouter
    api_router = APIRouter()
    payment_router = APIRouter()
    message_router = APIRouter()
    logger.warning("Using empty routers due to import failure")

from apscheduler.schedulers.background import BackgroundScheduler   
from services.sales_content_check import sales_content_changed
import uvicorn

from redis.asyncio import Redis
from services.cache_service import init_redis_client

# Define lifespan manager first
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
    # ========== REDIS CACHE INITIALIZATION ==========
        # Redis initialization
        try:
            redis = Redis.from_url(settings.redis_url, decode_responses=True)
            init_redis_client(redis)
            logger.info("Redis connected successfully")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}. Continuing without Redis cache.")
            redis = None

    

        global hashes
        try:
            from services.bot_service import initialize_website_content, initialize_sales_content, load_hashes, check_for_updates, get_urls, check_index_stats
            hashes = load_hashes()
            stats = check_index_stats()
            website_count = stats["namespaces"].get("website", {}).get("vector_count", 0)
            logger.info(f"Website vector count: {website_count}")
            sales_count   = stats["namespaces"].get("sales",   {}).get("vector_count", 0)
            logger.info(f"Vector count : {stats['total_vector_count']}")
            if website_count == 0:
                await initialize_website_content()
                # await initialize_events_content()
        except Exception as e:
            logger.error(f"Failed to initialize vector/OpenAI services: {e}")
            logger.warning("Continuing without vector/OpenAI services")
            hashes = {}
        # if sales_count == 0:
        #     await initialize_sales_content()
        # if website_count == 0 and sales_count == 0:
        #     logger.info("Initializing pinecone")
        #     await initialize_website_content()
        #     await initialize_sales_content()
        # if await sales_content_changed():
        #     logger.info("Sales content changed, refreshing...")
        #     await initialize_sales_content()
        # Periodic refresh (async)
        async def refresh_task():
            logger.info("Starting periodic refresh task...")
            while True:
                logger.info("Sleeping for 24 hours before checking for updates...")
                await asyncio.sleep(86400)  # Wait 24 hours before each check
                logger.info("Checking for updates...")
                try:
                    await check_for_updates()
                    logger.info("Update check completed successfully.")
                except Exception as e:
                    logger.error(f"Error during periodic update check: {e}") 

        loop = asyncio.get_event_loop()
        loop.create_task(refresh_task())
        
        # Start Google Drive push notifications (webhooks) or fallback to polling
        try:
            from services.google_drive_sync_service import start_google_drive_sync_task
            from services.google_drive_watch_service import setup_google_drive_watch
            from config.settings import GOOGLE_DRIVE_SYNC_INTERVAL, GOOGLE_DRIVE_WEBHOOK_URL
            sync_interval = GOOGLE_DRIVE_SYNC_INTERVAL
            
            # Use polling by default (webhooks are optional)
            if GOOGLE_DRIVE_WEBHOOK_URL:
                logger.info(f"Google Drive webhook URL configured: {GOOGLE_DRIVE_WEBHOOK_URL}")
                # Set up push notifications (real-time)
                watch_success = await setup_google_drive_watch()
                if watch_success:
                    logger.info("✓ Google Drive push notifications enabled - real-time sync active")
                    # Enable polling as fallback with longer interval (webhooks are primary, polling is backup)
                    # This ensures sync happens even if webhooks fail or are delayed
                    fallback_interval = max(sync_interval, 30)  # At least 30 minutes, or use configured interval
                    loop.create_task(start_google_drive_sync_task(fallback_interval, enabled=True))
                    logger.info(f"  Polling fallback enabled (checking every {fallback_interval} minutes as backup)")
                else:
                    logger.warning("Failed to set up push notifications, falling back to polling")
                    # Fallback to polling if watch setup fails (check every 60 minutes)
                    loop.create_task(start_google_drive_sync_task(60, enabled=True))
            else:
                # No webhook URL - use polling (default behavior)
                loop.create_task(start_google_drive_sync_task(sync_interval, enabled=True))
                logger.info(f"✓ Google Drive polling enabled (checking every {sync_interval} minutes)")
                logger.info("  Polling will automatically sync images from Google Drive folders")
                logger.info("  To use webhooks instead, set CSA_GOOGLE_DRIVE_WEBHOOK_URL environment variable")
            
            # Perform immediate catch-up sync on startup to handle missed changes
            # This ensures images uploaded while server was down are synced immediately
            try:
                from services.google_drive_sync_service import sync_all_drive_folders
                logger.info("Performing startup catch-up sync to handle any missed changes...")
                # Run catch-up sync in background (don't block startup)
                loop.create_task(sync_all_drive_folders())
            except Exception as e:
                logger.warning(f"Failed to perform startup catch-up sync: {e}")
                # Continue startup - polling will catch up eventually
        except Exception as e:
            logger.warning(f"Failed to start Google Drive sync: {e}")
            logger.warning("Google Drive images will not sync automatically, but manual sync will still work")
        
        yield
    except Exception as e:
        logger.error(f"Error during lifespan startup: {e}")
        raise  # Re-raise if you want the app to fail on startup errors
    finally:
        # Cleanup resources in finally block to ensure they run even on errors
        if hasattr(app.state, 'scheduler'):
            app.state.scheduler.shutdown()
        if hasattr(app.state, 'redis'):
            app.state.redis.close()
        
        # Stop Google Drive watch channels on shutdown
        try:
            from services.google_drive_watch_service import stop_all_watch_channels
            await stop_all_watch_channels()
            logger.info("Stopped all Google Drive watch channels")
        except Exception as e:
            logger.warning(f"Error stopping watch channels: {e}")
        
        pass

# Create the FastAPI app once
app = FastAPI(
    title=settings.app_name,
    description="A web server for CSA SFO Website",
    version="1.0.0",
    openapi_url=f"{settings.api_v1_str}/openapi.json",
    docs_url=f"{settings.api_v1_str}/docs",
    redoc_url=f"{settings.api_v1_str}/redoc",
    debug=settings.debug,
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
app.include_router(payment_router, prefix="/api/v1")  # Add this line to include payments router
app.include_router(message_router, prefix="/api/v1")  # Add this line to include payments router

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Allows specific origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all HTTP methods (GET, POST, etc.)
    allow_headers=["*"],  # Allows all headers
)

# Add trusted host middleware
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]  # Configure this properly for production
)

# Custom middleware to handle OPTIONS requests
# async def custom_cors_middleware(request: Request, call_next):
#     if request.method == "OPTIONS":
#         response = Response(status_code=200)
#         origin = request.headers.get("origin")
#         req_method = request.headers.get("access-control-request-method")
#         req_headers = request.headers.get("access-control-request-headers")
#         if origin in origins:
#             response.headers["Access-Control-Allow-Origin"] = origin
#             response.headers["Access-Control-Allow-Methods"] = req_method or "POST, GET, OPTIONS"
#             # Reflect requested headers to satisfy strict preflights
#             if req_headers:
#                 response.headers["Access-Control-Allow-Headers"] = req_headers
#             else:
#                 response.headers["Access-Control-Allow-Headers"] = "content-type, authorization"
#             response.headers["Access-Control-Allow-Credentials"] = "true"
#         return response
    
#     # Process non-OPTIONS requests normally
#     response = await call_next(request)
#     origin = request.headers.get("origin")
#     if origin in origins:
#         response.headers["Access-Control-Allow-Origin"] = origin
#         response.headers["Vary"] = "Origin"
#         response.headers["Access-Control-Allow-Credentials"] = "true"
#         response.headers["Access-Control-Allow-Headers"] = "content-type, authorization"
#     return response

# Apply the custom middleware
# app.middleware("http")(custom_cors_middleware)

# @app.middleware("http")
# async def log_requests(request: Request, call_next):
#     logger.info(f"Request: {request.method} {request.url} Origin: {request.headers.get('origin')}")
#     response = await call_next(request)
#     return response

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(f"Global exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

# Global bot instance
# bot = WebContentProcessor()

# Flag to ensure processing runs only once
# startup_ran = False

# List of URLs to process on startup
# urls = get_urls()

# Include API router
app.include_router(api_router, prefix="/v1/routes")

# Debug routes for testing
@app.get("/")
async def root():
    return {"message": "CSA SFO Website Server is running!", "status": "healthy"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

@app.get("/wake")
async def wake():
    # Touch lightweight resources to ensure cold services are initialized
    return {"status": "awake", "timestamp": datetime.utcnow().isoformat()}

@app.get("/debug/routes")
async def debug_routes():
    routes = []
    for route in app.routes:
        if hasattr(route, 'methods'):
            routes.append({
                "path": route.path,
                "methods": list(route.methods),
                "name": getattr(route, 'name', 'Unknown')
            })
    return {"routes": routes, "total_routes": len(routes)}
    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )
