import os
from dotenv import load_dotenv

load_dotenv()

# OpenAI Configuration
OPENAI_API_KEY = os.getenv("CSA_OPENAI")
if not OPENAI_API_KEY:
    print("WARNING: CSA_OPENAI environment variable not set")

OPENAI_MODEL = os.getenv("CSA_OPENAI_MODEL", "gpt-4.1")

# OpenAI throttling
OPENAI_CONCURRENCY = int(os.getenv("CSA_OPENAI_CONCURRENCY", "3"))
OPENAI_MAX_BACKOFF_TIME = int(os.getenv("CSA_OPENAI_MAX_BACKOFF_TIME", "60"))

# Pinecone Configuration
PINECONE_API_KEY = os.getenv("CSA_PINECONE")
if not PINECONE_API_KEY:
    print("WARNING: CSA_PINECONE environment variable not set")

# Supabase Configuration
SUPABASE_URL = os.getenv("CSA_SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("CSA_SUPABASE_SERVICE_KEY")
SUPABASE_REDIRECT_URL = os.getenv("CSA_SUPABASE_REDIRECT_URL")
JWT_SECRET_KEY = os.getenv("CSA_JWT_SECRET_KEY")
SUPABASE_GOOGLE_PROVIDER = os.getenv("CSA_SUPABASE_GOOGLE_PROVIDER")

# LinkedIn OAuth Configuration
LINKEDIN_CLIENT_ID = os.getenv("CSA_LINKEDIN_CLIENT_ID")
LINKEDIN_CLIENT_SECRET = os.getenv("CSA_LINKEDIN_CLIENT_SECRET")

# Email Configuration
FROM_EMAIL = os.getenv("CSA_FROM_EMAIL")
TO_EMAIL = os.getenv("CSA_TO_EMAIL_1")
FROM_NAME = os.getenv("CSA_FROM_NAME")
MAILERSEND_API_KEY = os.getenv("CSA_MAILERSEND_API_KEY")
MAILERSEND_API = os.getenv("CSA_MAILERSEND_API")

# Teams Webhook Configuration
TEAMS_WEBHOOK_URL = os.getenv("CSA_TEAMS_WEBHOOK_URL")
TEAMS_WEBHOOK_URL_VAPI = os.getenv("CSA_TEAMS_WEBHOOK_URL_VAPI")

# VAPI Configuration
VAPI_KEY = os.getenv("CSA_VAPI_KEY")
ASSISTANT_ID = os.getenv("CSA_ASSISTANT_ID")
PHONE_NUMBER_ID = os.getenv("CSA_PHONE_NUMBER_ID")


# Rolling Window Configuration
ROLLING_WINDOW_MIN = os.getenv("CSA_ROLLING_WINDOW_MIN")

# Redis Configuration
REDIS_DB = os.getenv("CSA_REDIS_DB_IND", "0")
REDIS_HOST = os.getenv("CSA_REDIS_HOST_IND", "localhost")
REDIS_PORT = os.getenv("CSA_REDIS_PORT_IND", "6379")
REDIS_PASSWORD = os.getenv("CSA_REDIS_PASSWORD_IND", "")
REDIS_URL = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}"

# Stripe Configuration
STRIPE_SECRET_KEY = os.getenv("CSA_STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("CSA_STRIPE_WEBHOOK_SECRET")

# MCP Server Configuration
MCP_SERVER_URL = os.getenv("CSA_MCP_SERVER_URL", "https://csa-mcp-573977120798.us-east1.run.app/mcp")

# Frontend Configuration
FRONTEND_BASE_URL = os.getenv("CSA_FRONTEND_BASE_URL", "http://localhost:8080")

# LinkedIn OAuth MCP Configuration
LINKEDIN_REDIRECT_URI = os.getenv("CSA_LINKEDIN_REDIRECT_URI", "http://localhost:8000/v1/routes/linkedin/callback")

