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
        
        # Extract user data (including Supabase Auth ID for new users)
        user_id = body.get("id")  # Supabase Auth user ID (critical for new signups)
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
            # Check if user exists
            existing_user = supabase.table("users").select("id").eq("email", email).execute()
            
            # Determine provider based on available data
            # If linkedin_id is present, it's LinkedIn OAuth; otherwise OTP/email
            provider = "linkedin_oidc" if linkedin_id else body.get("provider", "email")
            
            # Prepare user data for upsert
            user_data = {
                "email": email,
                "name": name,
                "linkedin_id": linkedin_id,
                "headline": headline,
                "avatar_url": avatar_url,
                "company_name": company_name,
                "provider": provider,
                "last_login": datetime.utcnow().isoformat()
            }
            
            # If user exists, update ONLY if coming from OAuth (has linkedin_id) or completing profile
            if existing_user.data and len(existing_user.data) > 0:
                # User exists - check if it's a profile completion (name/company are null)
                existing_full = supabase.table("users").select("*").eq("email", email).execute()
                existing_data = existing_full.data[0] if existing_full.data else {}
                
                existing_name = existing_data.get("name")
                existing_company = existing_data.get("company_name")
                
                if linkedin_id:
                    # OAuth login - safe to update
                    logger.info(f"Updating existing user via OAuth: {email}")
                    result = supabase.table("users").update(user_data).eq("email", email).execute()
                elif not existing_name or not existing_company:
                    # OTP signup with incomplete profile - allow update
                    logger.info(f"Completing profile for existing user: {email} (name: {existing_name} -> {name}, company: {existing_company} -> {company_name})")
                    result = supabase.table("users").update(user_data).eq("email", email).execute()
                else:
                    # OTP signup for existing user with complete profile - don't update
                    logger.warning(f"⚠️ User {email} already exists with complete profile. Use login instead of signup.")
                    result = existing_full
                    # Don't actually update anything
            else:
                # New user - insert with the Supabase Auth ID
                if user_id:
                    user_data["id"] = user_id
                logger.info(f"Inserting new user: {email} with ID: {user_id}")
                result = supabase.table("users").insert(user_data).execute()
            
            # Remove None values from log output
            log_data = {k: v for k, v in user_data.items() if v is not None}
            logger.info(f"User data saved: {log_data}")
            
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
