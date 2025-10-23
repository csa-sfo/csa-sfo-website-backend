import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Header
from supabase import create_client, Client
import jwt
import logging

# Load environment variables from .env file
load_dotenv()

# Set up logging to print info and errors
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Get values from environment variables
SUPABASE_URL = os.getenv("CSA_SUPABASE_URL")
SUPABASE_KEY = os.getenv("CSA_SUPABASE_SERVICE_KEY")
JWT_SECRET_KEY = os.getenv("CSA_JWT_SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# Connect to Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Function to sign in user using Supabase email/password
def signin_user(email: str, password: str):
    try:
        result = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        logger.info(f"User {email} signed in successfully.")
        return result
    except Exception as e:
        logger.exception(f"Sign in failed for {email}: {e}")
        raise HTTPException(status_code=401, detail="Invalid email or password")

# Function to get admin data by email (for OTP-based admin login)
def get_admin_by_email(email: str):
    """
    Get admin data by email from admins table.
    Returns admin data if found.
    """
    try:
        # Query the admins table for the given email
        result = supabase.table("admins").select("id, name, email").eq("email", email).limit(1).execute()
        
        if not result.data:
            logger.warning(f"Admin not found for email: {email}")
            return None
        
        admin = result.data[0]
        logger.info(f"Admin {email} found successfully.")
        
        # Return admin data
        return {
            "id": admin["id"],
            "name": admin["name"],
            "email": admin["email"]
        }
        
    except Exception as e:
        logger.error(f"Failed to get admin data for {email}: {str(e)}")
        return None

# Function to generate JWT token for admin
def generate_admin_token(admin_data: dict):
    """
    Generate JWT token for authenticated admin.
    Contains minimal information for security.
    """
    try:
        payload = {
            "user_id": admin_data["id"],  # Use user_id instead of admin_id for consistency
            "email": admin_data["email"],
            "role": "admin",  # Add role field for admin verification
            "aud": "authenticated",
            "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        }
        
        token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=ALGORITHM)
        logger.info(f"JWT token generated for admin: {admin_data['email']}")
        return token
        
    except Exception as e:
        logger.exception(f"Token generation failed for admin {admin_data['email']}: {e}")
        raise HTTPException(status_code=500, detail="Token generation failed")

# Function to verify the JWT token from Authorization header
def verify_token(authorization: str = Header(None)):
    if not authorization:
        logger.warning("Authorization header is missing")
        raise HTTPException(status_code=401, detail="Authorization header missing")

    try:
        # Split the header into 'Bearer' and the actual token
        scheme, token = authorization.split(" ")
        if scheme.lower() != "bearer":
            logger.warning("Authorization scheme is not Bearer")
            raise HTTPException(status_code=401, detail="Invalid auth scheme")

        # Decode the token using secret key and algorithm
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[ALGORITHM],
            audience="authenticated"
        )

        logger.info(f"Token is valid for email: {payload.get('email')}")
        return payload

    except jwt.ExpiredSignatureError:
        logger.warning("Token has expired")
        raise HTTPException(status_code=401, detail="Token expired")

    except jwt.InvalidTokenError as e:
        logger.exception(f"Token is invalid: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")

# Function to verify admin JWT token
def verify_admin_token(authorization: str = Header(None)):
    """
    Verify JWT token specifically for admin users.
    Returns admin payload if token is valid and user is admin.
    """
    if not authorization:
        logger.warning("Authorization header is missing")
        raise HTTPException(status_code=401, detail="Authorization header missing")

    try:
        # Split the header into 'Bearer' and the actual token
        parts = authorization.split(" ")
        if len(parts) != 2:
            logger.warning(f"Invalid authorization header format. Parts: {len(parts)}")
            raise HTTPException(status_code=401, detail="Invalid authorization header format")
        
        scheme, token = parts
        if scheme.lower() != "bearer":
            logger.warning("Authorization scheme is not Bearer")
            raise HTTPException(status_code=401, detail="Invalid auth scheme")

        # Decode the token using secret key and algorithm
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[ALGORITHM],
            audience="authenticated"
        )

        # Check if the token contains admin role
        if payload.get("role") != "admin":
            logger.warning(f"Token does not have admin role: {payload.get('email')}")
            raise HTTPException(status_code=403, detail="Not an admin")

        logger.info(f"Admin token is valid for: {payload.get('email')}")
        return payload

    except jwt.ExpiredSignatureError:
        logger.warning("Admin token has expired")
        raise HTTPException(status_code=401, detail="Token expired")

    except jwt.InvalidTokenError as e:
        logger.exception(f"Admin token is invalid: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")

