import os
import re
from dotenv import load_dotenv

load_dotenv()

# OpenAI Configuration
OPENAI_API_KEY = os.getenv("CSA_OPENAI")
if not OPENAI_API_KEY:
    print("WARNING: CSA_OPENAI environment variable not set")

OPENAI_MODEL = os.getenv("CSA_OPENAI_MODEL", "gpt-4.1-mini")

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

# Supabase Database Connection String for APScheduler
# Constructs from CSA_SUPABASE_URL and CSA_SUPABASE_DB_PASSWORD
# Format: postgresql://postgres:[PASSWORD]@[PROJECT-REF].supabase.co:5432/postgres
SUPABASE_DB_URL = None
if SUPABASE_URL:
    # Check if CSA_SUPABASE_URL is already a database connection string
    if SUPABASE_URL.startswith("postgres://") or SUPABASE_URL.startswith("postgresql://"):
        SUPABASE_DB_URL = SUPABASE_URL.replace("postgres://", "postgresql://", 1)
    else:
        # Extract project reference from API URL (e.g., https://ganqwjbdeivsmyekvojt.supabase.co)
        # and construct database connection string
        match = re.search(r'https://([^.]+)\.supabase\.co', SUPABASE_URL)
        if match:
            project_ref = match.group(1)
            db_password = os.getenv("CSA_SUPABASE_DB_PASSWORD")
            if db_password:
                SUPABASE_DB_URL = f"postgresql://postgres:{db_password}@{project_ref}.supabase.co:5432/postgres"
            else:
                print("WARNING: CSA_SUPABASE_DB_PASSWORD not set. Cannot construct database connection string for APScheduler.")
                print("         Reminder and thank-you emails will not be sent at exact times after server restarts.")
                print("         To fix: Set CSA_SUPABASE_DB_PASSWORD in your .env file (get it from Supabase Dashboard > Settings > Database)")

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

# AWS SES Configuration
AWS_ACCESS_KEY_ID = os.getenv("CSA_AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("CSA_AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("CSA_AWS_REGION", "us-east-1")
AWS_SES_FROM_EMAIL = os.getenv("CSA_AWS_SES_FROM_EMAIL", FROM_EMAIL)
AWS_SES_FROM_NAME = os.getenv("CSA_AWS_SES_FROM_NAME", FROM_NAME)
FRONTEND_URL = os.getenv("CSA_FRONTEND_URL", "https://csasfo.com")
