import os
from dotenv import load_dotenv

load_dotenv()

# OpenAI Configuration
OPENAI_API_KEY = os.getenv("CSA_OPENAIIND")

# Pinecone Configuration
PINECONE_API_KEY = os.getenv("CSA_PINECONEIND")

# Supabase Configuration
SUPABASE_URL = os.getenv("CSA_SUPABASEURLIND")
SUPABASE_SERVICE_KEY = os.getenv("CSA_SUPABASESERVICEKEYIND")

# Email Configuration
FROM_EMAIL = os.getenv("CSA_FROMEMAILIND")
TO_EMAIL = os.getenv("CSA_TOEMAILIND1")
FROM_NAME = os.getenv("CSA_FROMNAMEIND")
MAILERSEND_API_KEY = os.getenv("CSA_MAILERSENDAPIKEYIND")
MAILERSEND_API = os.getenv("CSA_MAILERSEND_API")

# Teams Webhook Configuration
TEAMS_WEBHOOK_URL = os.getenv("CSA_TEAMSWEBHOOKURLIND")
TEAMS_WEBHOOK_URL_VAPI = os.getenv("CSA_TEAMSWEBHOOKURLVAPIIND")

# VAPI Configuration
VAPI_KEY = os.getenv("CSA_VAPIKEYIND")
ASSISTANT_ID = os.getenv("CSA_ASSISTANTIDIND")
PHONE_NUMBER_ID = os.getenv("CSA_PHONENUMBERIDIND")


# Rolling Window Configuration
ROLLING_WINDOW_MIN = os.getenv("CSA_ROLLINGWINDOWMININD")

# Redis Configuration
REDIS_DB = os.getenv("CSA_REDIS_DB_IND", "0")
REDIS_HOST = os.getenv("CSA_REDIS_HOST_IND", "localhost")
REDIS_PORT = os.getenv("CSA_REDIS_PORT_IND", "6379")
REDIS_PASSWORD = os.getenv("CSA_REDIS_PASSWORD_IND", "")
REDIS_URL = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}"