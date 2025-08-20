from pydantic import BaseModel, HttpUrl, EmailStr
from typing import List, Optional
from datetime import datetime
from uuid import UUID

# Request body for generating token using email & password
class TokenRequest(BaseModel):
    email: str         # User's email (as plain string)
    password: str      # User's password


# Response body containing JWT token and its type
class TokenResponse(BaseModel):
    access_token: str       # JWT access token returned after login
    token_type: str = "bearer"  # Type of token; default is "bearer"
# Request body used during user sign-in

class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    company_name: str
    role: str

class GoogleProfileRequest(BaseModel):
    email: EmailStr
    name: str
    company_name: str
    role: str

class SigninRequest(BaseModel):
    email: EmailStr      # Validated email format
    password: str        # Plain text password
 

