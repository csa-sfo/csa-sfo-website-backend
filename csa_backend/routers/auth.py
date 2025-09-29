from fastapi import APIRouter, HTTPException, Request, Header
from fastapi.responses import RedirectResponse
from supabase import create_client, Client
from models.user_models import SigninRequest, TokenRequest, TokenResponse
from services.auth_services import verify_token, signin_user, get_admin_by_email, generate_admin_token, verify_admin_token
from models.user_models import SignupRequest, GoogleProfileRequest, ExtraDetails
from datetime import datetime, timedelta
import os, json, jwt, requests
from fastapi import Depends
from dotenv import load_dotenv
import logging

auth_router = APIRouter()

# Set up basic logging configuration (you can customize the format and level)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment from .env if present
load_dotenv()

# Load environment variables for Supabase configuration and secrets
SUPABASE_URL = os.getenv("CSA_SUPABASE_URL")
SUPABASE_KEY = os.getenv("CSA_SUPABASE_SERVICE_KEY") 
SUPABASE_REDIRECT_URL = os.getenv("CSA_SUPABASE_REDIRECT_URL")

# OAuth provider for Supabase (e.g., "google")
PROVIDER = os.getenv("CSA_SUPABASE_GOOGLE_PROVIDER")  # service_role key recommended for admin privileges

# JWT configuration
JWT_SECRET_KEY = os.getenv("CSA_JWT_SECRET_KEY")  # Secret key used to encode/decode JWT tokens
ALGORITHM = "HS256"  # JWT signing algorithm
JWT_EXP_MINUTES = int(os.getenv("CSA_JWT_EXP_MINUTES", "60"))  # Default to 60 minutes if not set

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
    
@auth_router.post("/admin/check")
def check_admin_by_email(data: dict):
    """
    Check if an email belongs to an admin and generate admin token if found.
    Used by OTP login to determine user role and provide admin token.
    """
    try:
        email = data.get("email")
        if not email:
            return {"is_admin": False}
        
        logger.info(f"Checking admin status for email: {email}")
        
        # Use the service function to get admin data
        admin_data = get_admin_by_email(email)
        
        if admin_data:
            logger.info(f"Email {email} belongs to admin: {admin_data['name']}")
            
            # Generate admin token
            admin_token = generate_admin_token(admin_data)
            
            return {
                "is_admin": True,
                "admin": {
                    "id": admin_data["id"],
                    "email": admin_data["email"],
                    "name": admin_data["name"]
                },
                "admin_token": admin_token
            }
        else:
            logger.info(f"Email {email} is not an admin")
            return {"is_admin": False}
            
    except Exception as e:
        logger.error(f"Error checking admin status for {email}: {e}")
        raise HTTPException(status_code=500, detail=f"Error checking admin status: {e}")

@auth_router.post("/user/role")
def get_user_role(token_data: dict = Depends(verify_token)):
    """
    Get user role based on JWT token.
    Returns user role information from database.
    """
    try:
        user_id = token_data.get("user_id")
        email = token_data.get("email")
        
        if not user_id or not email:
            raise HTTPException(status_code=400, detail="Invalid token payload")
        
        logger.info(f"Getting role for user: {email}")
        
        # Check if user is an admin
        admin_data = get_admin_by_email(email)
        if admin_data:
            logger.info(f"User {email} is an admin")
            return {
                "role": "admin",
                "user_id": admin_data["id"],
                "email": admin_data["email"],
                "name": admin_data["name"]
            }
        
        # Check if user is a regular user
        try:
            user_result = supabase.table("users").select("id, name, email, company_name, role").eq("email", email).limit(1).execute()
            if user_result.data:
                user = user_result.data[0]
                logger.info(f"User {email} is a regular user")
                return {
                    "role": "user",
                    "user_id": user["id"],
                    "email": user["email"],
                    "name": user.get("name"),
                    "company_name": user.get("company_name"),
                    "job_role": user.get("role")
                }
        except Exception as e:
            logger.error(f"Error checking users table for {email}: {e}")
        
        # User not found in either table
        logger.warning(f"User {email} not found in admins or users tables")
        raise HTTPException(status_code=404, detail="User not found")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user role for {email}: {e}")
        raise HTTPException(status_code=500, detail="Error getting user role")

@auth_router.post("/admin/verify")
def verify_admin_token_endpoint(payload: dict = Depends(verify_admin_token)):
    """
    Verify admin JWT token and return admin information.
    """
    try:
        logger.info(f"Admin token verification for: {payload.get('email')}")
        
        return {
            "status": "ok",
            "admin": {
                "id": payload.get("admin_id"),
                "email": payload.get("email"),
                "name": payload.get("name"),
                "role": payload.get("role")
            }
        }
        
    except Exception as e:
        logger.error(f"Error during admin token verification: {e}")
        raise HTTPException(status_code=500, detail="Token verification failed")

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
        admin_resp = supabase.table("admins").select("id, email, name").eq("email", user.email).limit(1).execute()
        if admin_resp.data:
            logger.info(f"Authenticated user '{user.email}' is an admin.")
            admin_row = admin_resp.data[0]
            return {
                "access_token": result.session.access_token,
                "refresh_token": result.session.refresh_token,
                "user": {
                    "id": admin_row["id"],
                    "email": admin_row["email"],
                    "name": admin_row.get("name"),
                    "type": "admin",
                    "profile_completed": True
                }
            }
        # Step 3: Check if the email belongs to a regular user
        user_resp = supabase.table("users").select("id, email, name, company_name, role").eq("email", user.email).limit(1).execute()
        if user_resp.data:
            logger.info(f"Authenticated user '{user.email}' is a regular user.")
            row = user_resp.data[0]
            profile_completed = bool(row.get("company_name") and row.get("role"))
            return {
                "access_token": result.session.access_token,
                "refresh_token": result.session.refresh_token,
                "user": {
                    "id": row["id"],
                    "email": row["email"],
                    "name": row.get("name"),
                    "company_name": row.get("company_name"),
                    "role": row.get("role"),
                    "type": "user",
                    "profile_completed": profile_completed
                }
            }
        logger.warning(f"User {user.email} not found in admins or users tables.")
        raise HTTPException(status_code=403, detail="Unauthorized user")

    except Exception as e:
        logger.error(f"Error during basic login for {data.email}: {e}")
        raise HTTPException(status_code=500, detail=f"Error during basic login for {data.email}: {e}")
    
@auth_router.post("/signup/basic")
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
            logger.info(f"User {email_norm} already exists in users table.")
            raise HTTPException(status_code=400, detail="User already exists in users table")

        # 2. Create user in Supabase Auth
        new_auth_user = supabase.auth.admin.create_user({
            "email": email_norm,
            "password": data.password,
            "email_confirm": True
        })
        if not new_auth_user or not new_auth_user.user:
            logger.error(f"Failed to create user in auth.")
            raise HTTPException(status_code=500, detail="Failed to create user in auth")

        # 3. Insert into users table with additional details
        user_data = {
            "id": new_auth_user.user.id,
            "email": email_norm,
            "name": data.name,
        }
        insert_response = supabase.table("users").upsert(user_data, on_conflict="email").execute()

        if not insert_response:
            # Rollback auth user to avoid orphan account
            supabase.auth.admin.delete_user(new_auth_user.user.id)
            logger.error(f"Rollback successful for user {email_norm}.")
            raise HTTPException(status_code=500, detail="Failed to insert or update user in users table")

        # Generate JWT token with minimal information for security
        payload = {
            "user_id": new_auth_user.user.id,
            "email": email_norm,
            "aud": "authenticated",
            "exp": datetime.utcnow() + timedelta(minutes=JWT_EXP_MINUTES)
        }
        if not JWT_SECRET_KEY or not isinstance(JWT_SECRET_KEY, str) or JWT_SECRET_KEY.strip() == "":
            logger.error("CSA_JWT_SECRET_KEY is not configured")
            raise HTTPException(status_code=500, detail="Server misconfiguration: missing JWT secret")
        token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=ALGORITHM)
        logger.info(f"Token generated for user {email_norm}")
        return {"message": "Step 1 complete. Use this token for /signup/details.", "token": token}
    except Exception as e:
        logger.exception(f"Signup failed: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    
@auth_router.post("/google-profile")
def store_google_profile(data: GoogleProfileRequest):
    """
    Store extended user profile info after Google OAuth signup.
    """
    logger.info(f"Google signup for {data.email}")
    try:
        existing = supabase.table("users").select("id").eq("email", data.email).limit(1).execute()
        if existing.data:
            user_id = existing.data[0]["id"]
            logger.info(f"User {data.email} already registered")
        else:
            # Insert basic info
            profile = {
                "email": data.email,
                "name": data.name
            }
            resp = supabase.table("users").insert(profile).execute()
            user_id = resp.data[0]["id"]

        # Generate JWT token with minimal information for security
        payload = {
            "user_id": user_id,
            "email": data.email,
            "aud": "authenticated",
            "exp": datetime.utcnow() + timedelta(minutes=JWT_EXP_MINUTES)
        }
        if not JWT_SECRET_KEY or not isinstance(JWT_SECRET_KEY, str) or JWT_SECRET_KEY.strip() == "":
            logger.error("CSA_JWT_SECRET_KEY is not configured")
            raise HTTPException(status_code=500, detail="Server misconfiguration: missing JWT secret")
        token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=ALGORITHM)
        logger.info(f"Generated JWT token for user {data.email}")
        return {"message": "Step 1 complete. Use this token for /signup/details.", "token": token}

    except Exception as e:
        logger.error(f"Google signup failed: {e}")
        raise HTTPException(status_code=500, detail=f"Signup failed: {e}")
    
@auth_router.post("/signup/details")
def signup_details(data:ExtraDetails,token_data: dict = Depends(verify_token)):
    """
    Step 2: Add company and role for the user created in step 1.
    """
    logger.info("Adding signup details")
    try:
        # Extract token from "Bearer <token>"
        user_id = token_data.get("user_id")
        if not user_id:
            logging.error("No user ID provided in token.")
            raise HTTPException(status_code=401, detail="Invalid token")

        # Update user with company and role
        update_response = (
            supabase.table("users")
            .update({"company_name": data.company_name, "role": data.role})
            .eq("id", user_id)
            .execute()
        )

        if not update_response or len(update_response.data) == 0:
            raise HTTPException(status_code=404, detail="User not found or update failed")
        logger.info("Signup details added successfully.")
        return {"message": "Signup completed successfully!"}

    except Exception as e:
        logger.exception(f"Error in signup_details: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@auth_router.post("/user/details")
def update_user_details(data: ExtraDetails, authorization: str = Header(None)):
    """
    Update company_name and role for a logged-in user using the Supabase access token.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")

    try:
        scheme, token = authorization.split(" ")
        if scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Invalid auth scheme")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Authorization header")

    try:
        user_resp = supabase.auth.get_user(token)
        auth_user = user_resp.user
        if not auth_user:
            raise HTTPException(status_code=401, detail="Invalid access token")
    except Exception as e:
        logger.error(f"Supabase token verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid access token")

    try:
        update_response = (
            supabase.table("users")
            .update({"company_name": data.company_name, "role": data.role})
            .eq("id", auth_user.id)
            .execute()
        )
        if not update_response or len(update_response.data) == 0:
            raise HTTPException(status_code=404, detail="User not found or update failed")
        return {"message": "Details updated successfully"}
    except Exception as e:
        logger.error(f"Failed to update user details: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@auth_router.post("/is-profile-completed")
def basic_login(token_data: dict = Depends(verify_token)):
    try:
        logger.info(f"Checking if profile is completed for user {token_data.get('email')}")
        user_resp = supabase.table("users").select("id, email, name, company_name, role").eq("email", token_data.get("email")).limit(1).execute()
        if user_resp.data:
            row = user_resp.data[0]
            profile_completed = bool(row.get("company_name") and row.get("role"))
            return {"profile_completed": profile_completed}
        logger.warning(f"User {token_data.get('email')} not found in users tables.")
        raise HTTPException(status_code=403, detail="Unauthorized user")

    except Exception as e:
        logger.error(f"Error during basic login for {token_data.get('email')}: {e}")
        raise HTTPException(status_code=500, detail=f"Error during basic login for {token_data.get('email')}: {e}")