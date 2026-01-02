import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Settings(BaseSettings):
    # App Configuration
    app_name: str = "CSA SFO Website Server"
    debug: bool = False
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000
    api_v1_str: str = "/api/v1"
    
    # OpenAI Configuration
    openai_api_key: str
    
    # Pinecone Configuration
    pinecone_api_key: str
    
    # Supabase Configuration
    supabase_url: str
    supabase_service_key: str
    supabase_redirect_url: Optional[str] = None
    jwt_secret_key: str
    supabase_google_provider: Optional[str] = None
    
    # Email Configuration
    from_email: Optional[str] = None
    to_email: Optional[str] = None
    from_name: Optional[str] = None
    mailersend_api_key: Optional[str] = None
    mailersend_api: Optional[str] = None
    
    # Teams Webhook Configuration
    teams_webhook_url: Optional[str] = None
    teams_webhook_url_vapi: Optional[str] = None
    
    # VAPI Configuration
    vapi_key: Optional[str] = None
    assistant_id: Optional[str] = None
    phone_number_id: Optional[str] = None
    
    # Rolling Window Configuration
    rolling_window_min: Optional[str] = None
    
    # Redis Configuration
    redis_db: str = "0"
    redis_host: str = "localhost"
    redis_port: str = "6379"
    redis_password: str = ""
    
    # Stripe Configuration
    stripe_secret_key: Optional[str] = None
    stripe_webhook_secret: Optional[str] = None
    
    # AWS SES Configuration
    aws_access_key_id: Optional[str] = Field(default=None, env="CSA_AWS_ACCESS_KEY_ID")
    aws_secret_access_key: Optional[str] = Field(default=None, env="CSA_AWS_SECRET_ACCESS_KEY")
    aws_region: Optional[str] = Field(default=None, env="CSA_AWS_REGION")
    aws_ses_from_email: Optional[str] = Field(default=None, env="CSA_AWS_SES_FROM_EMAIL")
    aws_ses_from_name: Optional[str] = Field(default=None, env="CSA_AWS_SES_FROM_NAME")
    frontend_url: Optional[str] = Field(default=None, env="CSA_FRONTEND_URL")
    
    @property
    def redis_url(self) -> str:
        """Build Redis URL from components."""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
    
    class Config:
        env_file = ".env"
        env_prefix = "CSA_"
        case_sensitive = False
        # Allow extra fields for AWS (which don't have CSA_ prefix)
        extra = "ignore"

# Create settings instance
try:
    settings = Settings()
    print("✅ All required environment variables loaded successfully")
except Exception as e:
    print(f"❌ Failed to load environment variables: {e}")
    print("Please check your .env file or environment variables")
    raise
