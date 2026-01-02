# Standard library imports
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
import uvicorn

# Local application imports
from app.config_simple import settings
from services.bot_service import (
    check_for_updates,
    check_index_stats,
    get_urls,
    initialize_events_content,
    initialize_sales_content,
    initialize_website_content,
    load_hashes,
)
from services.cache_service import init_redis_client
from services.event_email_scheduler import (
    process_reminder_emails_for_tomorrow,
    process_thank_you_emails_for_yesterday,
)
from services.sales_content_check import sales_content_changed

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
except ImportError as e:
    logger.error(f"Failed to import required modules: {e}")
    # Create empty routers if imports fail
    api_router = APIRouter()
    payment_router = APIRouter()
    message_router = APIRouter()
    logger.warning("Using empty routers due to import failure")

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
        # Periodic refresh and email automation (async)
        async def refresh_task():
            logger.info("Starting periodic refresh task...")
            while True:
                logger.info("Sleeping for 24 hours before checking for updates and sending emails...")
                await asyncio.sleep(86400)  # Wait 24 hours before each check
                logger.info("Checking for updates and processing emails...")
                try:
                    # Check for content updates
                    await check_for_updates()
                    logger.info("Update check completed successfully.")
                    
                    # Send reminder emails for events happening tomorrow
                    try:
                        reminders_sent = await process_reminder_emails_for_tomorrow()
                        if reminders_sent > 0:
                            logger.info(f"Sent {reminders_sent} reminder emails for events tomorrow")
                    except Exception as e:
                        logger.error(f"Error sending reminder emails: {e}")
                    
                    # Send thank-you emails for events that completed yesterday
                    try:
                        thank_yous_sent = await process_thank_you_emails_for_yesterday()
                        if thank_yous_sent > 0:
                            logger.info(f"Sent {thank_yous_sent} thank-you emails for events yesterday")
                    except Exception as e:
                        logger.error(f"Error sending thank-you emails: {e}")
                        
                except Exception as e:
                    logger.error(f"Error during periodic update check: {e}") 

        loop = asyncio.get_event_loop()
        loop.create_task(refresh_task())
        
        yield
    except Exception as e:
        logger.error(f"Error during lifespan startup: {e}")
        raise  # Re-raise if you want the app to fail on startup errors
    finally:
        # Cleanup resources in finally block to ensure they run even on errors
        if hasattr(app.state, 'redis'):
            app.state.redis.close()

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
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )
