from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from supabase import create_client, Client
from datetime import datetime
import os
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize router
linkedin_router = APIRouter()

# Load environment variables for Supabase configuration
SUPABASE_URL = os.getenv("CSA_SUPABASE_URL")
SUPABASE_KEY = os.getenv("CSA_SUPABASE_SERVICE_KEY")
SUPABASE_REDIRECT_URL = os.getenv("CSA_SUPABASE_REDIRECT_URL")

# Load LinkedIn OAuth configuration
LINKEDIN_CLIENT_ID = os.getenv("CSA_LINKEDIN_CLIENT_ID")
LINKEDIN_CLIENT_SECRET = os.getenv("CSA_LINKEDIN_CLIENT_SECRET")

# Validate LinkedIn configuration
if not LINKEDIN_CLIENT_ID:
    logger.warning("CSA_LINKEDIN_CLIENT_ID environment variable not set")
if not LINKEDIN_CLIENT_SECRET:
    logger.warning("CSA_LINKEDIN_CLIENT_SECRET environment variable not set")

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


@linkedin_router.get("/linkedin-login")
def linkedin_login():
    """Redirects users to LinkedIn's OAuth consent screen via Supabase."""
    logger.info("LinkedIn OAuth login initiated.")
    
    # Validate LinkedIn configuration
    if not LINKEDIN_CLIENT_ID or not LINKEDIN_CLIENT_SECRET:
        logger.error("LinkedIn OAuth configuration missing")
        raise HTTPException(status_code=500, detail="LinkedIn OAuth not configured")
    
    # Construct Supabase OAuth URL for LinkedIn
    # Redirect directly to frontend since Supabase returns access_token in URL hash
    # Note: Supabase only supports linkedin_oidc which provides limited profile data
    frontend_base_url = os.getenv("FRONTEND_BASE_URL", "http://localhost:8081")
    linkedin_callback_url = f"{frontend_base_url}/linkedin-callback"
    login_url = f"{SUPABASE_URL}/auth/v1/authorize?provider=linkedin_oidc&redirect_to={linkedin_callback_url}"
    return RedirectResponse(url=login_url)


@linkedin_router.get("/linkedin-callback")
def linkedin_callback(request: Request):
    """
    Handles Supabase OAuth LinkedIn callback.
    Extracts access_token, verifies user, saves to users table, and returns user details.
    """
    logger.info("LinkedIn OAuth callback initiated.")

    # Step 1: Check for error parameters first
    error = request.query_params.get("error")
    error_description = request.query_params.get("error_description")
    
    if error:
        logger.error(f"LinkedIn OAuth error: {error} - {error_description}")
        raise HTTPException(status_code=400, detail=f"LinkedIn OAuth error: {error_description or 'User cancelled authorization'}")

    # Step 2: Since we're now using Supabase client-side OAuth,
    # this callback is no longer needed, but kept for backward compatibility
    # The frontend handles the OAuth flow directly using Supabase client
    
    frontend_base_url = os.getenv("FRONTEND_BASE_URL", "http://localhost:8081")
    frontend_callback_url = f"{frontend_base_url}/linkedin-callback"
    
    logger.info(f"Redirecting to frontend callback: {frontend_callback_url}")
    return RedirectResponse(url=frontend_callback_url)


@linkedin_router.post("/upsert")
async def upsert_linkedin_user(request: Request):
    """
    Upserts LinkedIn user data into the users table.
    Called from frontend after successful OAuth.
    Also checks admins table to determine if user is an admin.
    """
    try:
        # Get the request body
        body = await request.json()
        logger.info(f"Received upsert request: {body}")
        
        # Extract LinkedIn user data
        email = body.get("email")
        name = body.get("name")
        linkedin_id = body.get("linkedin_id")
        headline = body.get("headline", "")
        avatar_url = body.get("avatar_url", "")
        company_name = body.get("company_name", "")
        
        if not email:
            raise HTTPException(status_code=400, detail="Email is required")
        
        # Check if user is an admin FIRST (before upserting to users table)
        is_admin = False
        try:
            admin_check = supabase.table("admins").select("id, email, name").eq("email", email).limit(1).execute()
            if admin_check.data and len(admin_check.data) > 0:
                is_admin = True
                logger.info(f"✅ User {email} is an admin - skipping users table upsert")
            else:
                logger.info(f"ℹ️ User {email} is not an admin")
        except Exception as admin_error:
            logger.error(f"❌ Error checking admin status: {admin_error}")
            # Continue even if admin check fails
        
        # Only upsert to users table if NOT an admin
        result = None
        if not is_admin:
            # Prepare user data for upsert
            user_data = {
                "email": email,
                "name": name,
                "linkedin_id": linkedin_id,
                "headline": headline,
                "avatar_url": avatar_url,
                "company_name": company_name,
                "provider": "linkedin_oidc",
                "last_login": datetime.utcnow().isoformat()
            }
            
            # Remove None values
            user_data = {k: v for k, v in user_data.items() if v is not None}
            
            logger.info(f"Upserting user data: {user_data}")
            
            # Upsert into users table
            result = supabase.table("users").upsert(
                user_data,
                on_conflict="email"
            ).execute()
            
            logger.info(f"✅ User data upserted successfully for {email}")
        else:
            logger.info(f"⏭️ Skipping users table upsert for admin {email}")
        
        return {
            "success": True,
            "message": "User data saved successfully" if not is_admin else "Admin login successful",
            "user": result.data[0] if result and result.data else None,
            "is_admin": is_admin,
            "role": "admin" if is_admin else "user"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error upserting LinkedIn user: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upsert user data: {str(e)}")


@linkedin_router.get("/linkedin-health")
def linkedin_health():
    """Health check endpoint for LinkedIn OAuth."""
    return {
        "status": "ok", 
        "service": "linkedin-oauth",
        "client_id_configured": bool(LINKEDIN_CLIENT_ID),
        "client_secret_configured": bool(LINKEDIN_CLIENT_SECRET),
        "supabase_configured": bool(SUPABASE_URL and SUPABASE_KEY)
    }


@linkedin_router.get("/linkedin-config")
def linkedin_config():
    """Get LinkedIn OAuth configuration status (without exposing secrets)."""
    return {
        "client_id": LINKEDIN_CLIENT_ID[:8] + "..." if LINKEDIN_CLIENT_ID else None,
        "client_secret_configured": bool(LINKEDIN_CLIENT_SECRET),
        "supabase_url": SUPABASE_URL,
        "redirect_url": SUPABASE_REDIRECT_URL,
        "status": "configured" if (LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET) else "incomplete"
    }
