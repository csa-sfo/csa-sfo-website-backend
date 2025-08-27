import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Settings:
    """Simple settings class without external dependencies."""
    
    def __init__(self):
        # App Configuration
        self.app_name = "CSA SFO Website Server"
        self.debug = os.getenv("CSA_DEBUG", "false").lower() == "true"
        self.log_level = os.getenv("CSA_LOG_LEVEL", "INFO")
        self.host = os.getenv("CSA_HOST", "0.0.0.0")
        self.port = int(os.getenv("CSA_PORT", "8000"))
        self.api_v1_str = os.getenv("CSA_API_V1_STR", "/api/v1")
        
        # OpenAI Configuration
        self.openai_api_key = os.getenv("CSA_OPENAI")
        if not self.openai_api_key:
            raise ValueError("CSA_OPENAI environment variable is required")
        
        # Pinecone Configuration
        self.pinecone_api_key = os.getenv("CSA_PINECONE")
        if not self.pinecone_api_key:
            raise ValueError("CSA_PINECONE environment variable is required")
        
        # Supabase Configuration
        self.supabase_url = os.getenv("CSA_SUPABASE_URL")
        if not self.supabase_url:
            raise ValueError("CSA_SUPABASE_URL environment variable is required")
            
        self.supabase_service_key = os.getenv("CSA_SUPABASE_SERVICE_KEY")
        if not self.supabase_service_key:
            raise ValueError("CSA_SUPABASE_SERVICE_KEY environment variable is required")
            
        self.supabase_redirect_url = os.getenv("CSA_SUPABASE_REDIRECT_URL")
        self.jwt_secret_key = os.getenv("CSA_JWT_SECRET_KEY")
        if not self.jwt_secret_key:
            raise ValueError("CSA_JWT_SECRET_KEY environment variable is required")
            
        self.supabase_google_provider = os.getenv("CSA_SUPABASE_GOOGLE_PROVIDER")
        
        # Email Configuration
        self.from_email = os.getenv("CSA_FROM_EMAIL")
        self.to_email = os.getenv("CSA_TO_EMAIL")
        self.from_name = os.getenv("CSA_FROM_NAME")
        self.mailersend_api_key = os.getenv("CSA_MAILERSEND_API_KEY")
        self.mailersend_api = os.getenv("CSA_MAILERSEND_API")
        
        # Teams Webhook Configuration
        self.teams_webhook_url = os.getenv("CSA_TEAMS_WEBHOOK_URL")
        self.teams_webhook_url_vapi = os.getenv("CSA_TEAMS_WEBHOOK_URL_VAPI")
        
        # VAPI Configuration
        self.vapi_key = os.getenv("CSA_VAPI_KEY")
        self.assistant_id = os.getenv("CSA_ASSISTANT_ID")
        self.phone_number_id = os.getenv("CSA_PHONE_NUMBER_ID")
        
        # Rolling Window Configuration
        self.rolling_window_min = os.getenv("CSA_ROLLING_WINDOW_MIN")
        
        # Redis Configuration
        self.redis_db = os.getenv("CSA_REDIS_DB", "0")
        self.redis_host = os.getenv("CSA_REDIS_HOST", "localhost")
        self.redis_port = os.getenv("CSA_REDIS_PORT", "6379")
        self.redis_password = os.getenv("CSA_REDIS_PASSWORD", "")
        
        # Stripe Configuration
        self.stripe_secret_key = os.getenv("CSA_STRIPE_SECRET_KEY")
        self.stripe_webhook_secret = os.getenv("CSA_STRIPE_WEBHOOK_SECRET")
    
    @property
    def redis_url(self) -> str:
        """Build Redis URL from components."""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

# Create settings instance
try:
    settings = Settings()
    print("✅ All required environment variables loaded successfully")
except Exception as e:
    print(f"❌ Failed to load environment variables: {e}")
    print("Please check your .env file or environment variables")
    raise
