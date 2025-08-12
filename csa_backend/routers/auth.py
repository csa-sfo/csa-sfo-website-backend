from fastapi import APIRouter, HTTPException, Request, Header
from fastapi.responses import RedirectResponse
from supabase import create_client, Client
from models.user_models import SigninRequest, TokenRequest, TokenResponse
from services.auth_services import verify_token, signin_user
from models.user_models import SignupRequest, GoogleProfileRequest
import os, json, jwt, requests
from fastapi import Depends
import logging

auth_router = APIRouter()

# Set up basic logging configuration (you can customize the format and level)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables for Supabase configuration and secrets
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") 
SUPABASE_REDIRECT_URL = os.getenv("SUPABASE_REDIRECT_URL")

# OAuth provider for Supabase (e.g., "google")
PROVIDER = os.getenv("SUPABASE_GOOGLE_PROVIDER")  # service_role key recommended for admin privileges

# JWT configuration
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")  # Secret key used to encode/decode JWT tokens
ALGORITHM = "HS256"  # JWT signing algorithm

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


@auth_router.get("/google-login")
def google_login():
    """Redirects users to Google's OAuth consent screen."""
    login_url = f"{SUPABASE_URL}/auth/v1/authorize?provider=google&redirect_to={SUPABASE_REDIRECT_URL}"
    return RedirectResponse(url=login_url)

@auth_router.get("/callback")
def google_callback(request: Request):
    """
    Handles Supabase OAuth Google callback.
    Extracts access_token, verifies user, and returns user details.
    """

    logger.info("Google OAuth callback initiated.")

    # Step 1: Get access token from query parameters
    access_token = request.query_params.get("access_token")
    if not access_token:
        logger.error("Missing access token in Google callback.")
        raise HTTPException(status_code=400, detail="Missing access token")

    logger.info("Access token received.")

    # Step 2: Retrieve user info from Supabase Auth
    try:
        user_resp = supabase.auth.get_user(access_token)
        user = user_resp.user
    except Exception as e:
        logger.error(f"Error retrieving user from Supabase: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve user info")

    if not user:
        logger.warning("Invalid access token or user not found.")
        raise HTTPException(status_code=401, detail="Invalid user")

    logger.info(f"User authenticated: {user.email}")

    # Step 3: Check if user is an Admin
    try:
        admin_data = (
            supabase.table("admins")
            .select("id, email, name")
            .eq("email", user.email)
            .limit(1)
            .execute()
        )
    except Exception as e:
        logger.error(f"Database query failed for admins table: {e}")
        raise HTTPException(status_code=500, detail="Admin data lookup failed")

    if not admin_data.data:
        logger.warning(f"User not registered in 'admins' table: {user.email}")
        raise HTTPException(status_code=403, detail="Unauthorized user")

    # Step 4: Check if user exists in users table if not found in admins
    if admin_data.data:
        logger.info(f"User {user.email} found in admins table.")
        return {
            "access_token": access_token,
            "role": "admin",
            "user": admin_data.data[0]
        }
    else:
        try:
            user_data = (
                supabase.table("users")
                .select("id, name, email")
                .eq("email", user.email)
                .limit(1)
                .execute()
            )
        except Exception as e:
            logger.error(f"Database query failed for users table: {e}")
            raise HTTPException(status_code=500, detail="User data lookup failed")

        if user_data.data:
            logger.info(f"User {user.email} found in users table.")
            return {
                "access_token": access_token,
                "role": "user",
                "user": user_data.data[0]
            }
        else:
            logger.warning(f"User {user.email} not found in either table.")
            raise HTTPException(status_code=403, detail="Unauthorized user")
    
@auth_router.post("/auth/verify-admin")
def verify_admin(payload: dict = Depends(verify_token)):
    """
    Verifies if the user from token payload is an admin.
    Token is validated by `verify_token` dependency.
    """

    # Step 1: Extract email from token payload
    email = payload.get("email")
    if not email:
        logger.info("Invalid token payload: missing email.")
        raise HTTPException(status_code=403, detail="Invalid token payload")

    logger.info(f"Verifying if user '{email}' is an admin.")

    # Step 2: Look up user in Supabase 'admins' table
    try:
        res = (
            supabase.table("admins")
            .select("*")
            .eq("email", email)
            .limit(1)
            .execute()
        )
    except Exception as e:
        logger.exception(f"Database error while checking admin status for {email}")
        raise HTTPException(status_code=500, detail="Internal server error")

    # Step 3: Check if user is found
    if not res.data:
        logger.info(f"User '{email}' is not found or not an admin.")
        raise HTTPException(status_code=403, detail="Not an admin")

    if res.data[0]["role"] != "admin":
        logger.info(f"User '{email}' does not have admin role.")
        raise HTTPException(status_code=403, detail="Not an admin") 

    user = res.data[0]
    logger.info(f"User '{email}' verified as admin.")
    return {
        "status": "ok"
    }

@auth_router.post("/login")
def basic_login(data: SigninRequest):
    """
    Perform basic email/password sign-in using Supabase Auth.
    Returns access and refresh tokens on success.
    """

    try:
        # Step 1: Attempt to sign in user using email/password
        result = signin_user(data.email, data.password)
        user = result.user

        # Step 2: If user not found, raise HTTP 401 Unauthorized
        if not user:
            logger.info(f"Failed login attempt for email: {data.email}")
            raise HTTPException(status_code=401, detail="Invalid credentials")

        logger.info(f"User '{user.email}' logged in successfully.")

        # Step 2: Check if the email belongs to an admin
        admin_resp = supabase.table("admins").select("*").eq("email", user.email).limit(1).execute()
        if admin_resp.data:
            logger.info(f"Authenticated user '{user.email}' is an admin.")
            return {
                "access_token": result.session.access_token,
                "refresh_token": result.session.refresh_token,
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "type": "admin"
                }
            }
        # Step 3: Check if the email belongs to a regular user
        user_resp = supabase.table("users").select("*").eq("email", user.email).limit(1).execute()
        if user_resp.data:
            logger.info(f"Authenticated user '{user.email}' is a regular user.")
            return {
                "access_token": result.session.access_token,
                "refresh_token": result.session.refresh_token,
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "type": "user"
                }
            }
        logger.warning(f"User {user.email} not found in admins or users tables.")
        raise HTTPException(status_code=403, detail="Unauthorized user")

    except Exception as e:
        logger.error(f"Error during basic login for {data.email}: {e}")
        raise HTTPException(status_code=500, detail=f"Error during basic login for {data.email}: {e}")
    
@auth_router.post("/signup")
def signup(data: SignupRequest):
    """
    Register user using Supabase Auth and store extended profile in 'users' table.
    """
    email_norm = data.email.strip().lower()
    logger.info(f"Signup attempt for email: {email_norm}")
    try:
        # 1. Check if user already exists in users table
        user_check = supabase.table("users").select("id").eq("email", email_norm).execute()
        if user_check.data and len(user_check.data) > 0:
            raise HTTPException(status_code=400, detail="User already exists in users table")

        # 2. Create user in Supabase Auth
        new_auth_user = supabase.auth.admin.create_user({
            "email": email_norm,
            "password": data.password,
            "email_confirm": True
        })
        if not new_auth_user or not new_auth_user.user:
            raise HTTPException(status_code=500, detail="Failed to create user in auth")

        # 3. Insert into users table with additional details
        user_data = {
            "id": new_auth_user.user.id,
            "email": email_norm,
            "company_name": data.company_name,
            "role": data.role,
        }
        insert_response = supabase.table("users").upsert(user_data, on_conflict="email").execute()

        if not insert_response:
            # Rollback auth user to avoid orphan account
            supabase.auth.admin.delete_user(new_auth_user.user.id)
            raise HTTPException(status_code=500, detail="Failed to insert or update user in users table")
        return {"message": "User created successfully", "user_id": new_auth_user.user.id}

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    
@auth_router.post("/google-profile")
def store_google_profile(data: GoogleProfileRequest):
    """
    Store extended user profile info after Google OAuth signup.
    """
    logger.info(f"Storing Google profile for email: {data.email}")
    # Check if already exists to avoid duplicates
    try:
        existing = supabase.table("users").select("id").eq("email", data.email).limit(1).execute()
        if existing.data:
            logger.info(f"User {data.email} already registered.")
            return {"message": "User already registered"}

        # Insert extended info
        profile = {
            "email": data.email,
            "name": data.name,
            "company_name": data.company_name,
            "role": data.role
        }

        response = supabase.table("users").insert(profile).execute()
        if not response:
            logger.error(f"Failed to insert Google profile: {response.error.message}")
            raise HTTPException(status_code=500, detail="Failed to save Google profile")

        return {"message": "Google signup profile saved",
            "user": response.data[0]}
    except Exception as e:
        logger.error(f"Error storing Google profile for {data.email}: {e}")
        raise HTTPException(status_code=500, detail=f"Signup failed: {e}")    


