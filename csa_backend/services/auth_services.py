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
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key")
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
    

