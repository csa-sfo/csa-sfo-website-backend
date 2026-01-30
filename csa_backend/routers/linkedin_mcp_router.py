from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import RedirectResponse
from supabase import create_client, Client
from services.fastmcp_service import get_current_user, call_mcp_tool
from services.social_automation_service import get_social_automation_service
from config.settings import SUPABASE_URL, SUPABASE_SERVICE_KEY, LINKEDIN_REDIRECT_URI, FRONTEND_BASE_URL
from datetime import datetime, timedelta
import logging
import secrets
import os
import requests
import base64
import json
import re
import uuid as uuid_lib
from urllib.parse import urlparse
from dotenv import load_dotenv
from typing import Dict, Any, Optional

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize router
linkedin_mcp_router = APIRouter()

# Use redirect URI from settings
REDIRECT_URI = LINKEDIN_REDIRECT_URI

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


@linkedin_mcp_router.get("/linkedin/connect")
async def linkedin_connect(request: Request, current_user: dict = Depends(get_current_user)):
    """
    Initiate LinkedIn OAuth flow by calling MCP linkedin_get_login_url.
    Returns a redirect response to LinkedIn's authorization URL.
    Stores state->user_id mapping in Supabase for callback retrieval.
    If Accept header is application/json, returns JSON with the URL instead of redirecting.
    """
    try:
        user_id = current_user.get("user_id")
        email = current_user.get("email")
        
        if not user_id:
            raise HTTPException(
                status_code=400,
                detail="User ID not found in token"
            )
        
        # Generate a state parameter that includes user_id for callback retrieval
        # Store state->user_id mapping in Supabase
        state = secrets.token_urlsafe(32)
        
        # Store state->user_id mapping in Supabase (using oauth_states table or similar)
        # For simplicity, we'll use a temporary table or store in cache
        # For now, we'll encode user_id in state or use a mapping table
        # Store state with user_id (expires in 10 minutes)
        try:
            expires_at = datetime.utcnow() + timedelta(seconds=600)  # 10 minutes
            supabase.table("oauth_states").insert({
                "state": state,
                "user_id": user_id,
                "created_at": datetime.utcnow().isoformat(),
                "expires_at": expires_at.isoformat()
            }).execute()
        except Exception:
            pass
        
        # Call MCP server to get login URL with our state
        result = await call_mcp_tool(
            "linkedin_get_login_url",
            {
                "redirect_uri": REDIRECT_URI,
                "state": state,
                "scopes": None  # MCP will use default scopes if None
            }
        )
        
        # Extract the URL from the result
        login_url = result.get("url")
        if not login_url:
            raise HTTPException(
                status_code=500,
                detail="MCP server did not return a login URL"
            )
        
        # Check if client wants JSON response (for frontend to handle redirect)
        accept_header = request.headers.get("accept", "")
        if "application/json" in accept_header:
            return {"url": login_url, "state": state}
        
        return RedirectResponse(url=login_url)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error initiating LinkedIn OAuth: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initiate LinkedIn OAuth: {str(e)}"
        )


@linkedin_mcp_router.get("/linkedin/callback")
async def linkedin_callback(request: Request, code: str = None, state: str = None, error: str = None):
    """
    Handle LinkedIn OAuth callback.
    Calls MCP linkedin_exchange_code and stores tokens in Supabase.
    Retrieves user_id from state mapping stored during /linkedin/connect.
    This route is registered under /v1/routes/linkedin/callback.
    """
    try:
        # Check for OAuth errors
        if error:
            logger.error(f"LinkedIn OAuth error: {error}")
            raise HTTPException(
                status_code=400,
                detail=f"LinkedIn OAuth error: {error}"
            )
        
        if not code:
            logger.error("No authorization code received from LinkedIn")
            raise HTTPException(
                status_code=400,
                detail="No authorization code received"
            )
        
        if not state:
            logger.error("No state parameter received from LinkedIn")
            raise HTTPException(
                status_code=400,
                detail="No state parameter received"
            )
        
        # Retrieve user_id from state mapping
        user_id = None
        try:
            state_result = supabase.table("oauth_states").select("user_id").eq("state", state).limit(1).execute()
            if state_result.data and len(state_result.data) > 0:
                user_id = state_result.data[0].get("user_id")
                # Delete used state (one-time use)
                supabase.table("oauth_states").delete().eq("state", state).execute()
        except Exception:
            pass
        
        if not user_id:
            raise HTTPException(
                status_code=400,
                detail="Invalid or expired state parameter. Please try connecting again."
            )
        
        # Call MCP server to exchange code for tokens
        token_result = await call_mcp_tool(
            "linkedin_exchange_code",
            {
                "code": code,
                "redirect_uri": REDIRECT_URI
            }
        )
        
        # Extract tokens from the result
        access_token = token_result.get("access_token")
        refresh_token = token_result.get("refresh_token")
        expires_in = token_result.get("expires_in", 3600)  # Default to 1 hour if not provided
        
        if not access_token:
            raise HTTPException(
                status_code=500,
                detail="MCP server did not return an access token"
            )
        
        # Calculate expiration time
        expires_at = datetime.utcnow().timestamp() + expires_in
        
        # Store tokens in Supabase (upsert to handle reconnection)
        try:
            token_data = {
                "user_id": user_id,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_at": expires_at,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
            
            # Upsert tokens (update if exists, insert if not)
            supabase.table("linkedin_tokens").upsert(
                token_data,
                on_conflict="user_id"
            ).execute()
            
        except Exception as e:
            logger.error(f"Error storing LinkedIn tokens in Supabase: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to store LinkedIn tokens: {str(e)}"
            )
        
        # Redirect to frontend Admin page social media section
        redirect_url = f"{FRONTEND_BASE_URL}/admin?linkedin=connected"
        return RedirectResponse(url=redirect_url)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error handling LinkedIn callback: {e}")
        # Redirect to frontend with error parameter
        redirect_url = f"{FRONTEND_BASE_URL}/admin?linkedin=error"
        return RedirectResponse(url=redirect_url)


@linkedin_mcp_router.get("/linkedin/status")
async def linkedin_status(current_user: dict = Depends(get_current_user)):
    """
    Check LinkedIn connection status for the current user.
    Returns whether the user has valid LinkedIn tokens.
    """
    try:
        user_id = current_user.get("user_id")
        email = current_user.get("email")
        
        if not user_id:
            raise HTTPException(
                status_code=400,
                detail="User ID not found in token"
            )
        
        # Check if user has LinkedIn tokens
        token_result = supabase.table("linkedin_tokens").select("access_token, expires_at").eq("user_id", user_id).limit(1).execute()
        
        if not token_result.data or len(token_result.data) == 0:
            return {
                "connected": False,
                "message": "LinkedIn not connected"
            }
        
        token_data = token_result.data[0]
        access_token = token_data.get("access_token")
        expires_at = token_data.get("expires_at")
        
        # Check if token is expired
        is_expired = False
        if expires_at and datetime.utcnow().timestamp() > expires_at:
            is_expired = True
        
        return {
            "connected": True,
            "expired": is_expired,
            "has_token": bool(access_token)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking LinkedIn status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check LinkedIn status: {str(e)}"
        )


@linkedin_mcp_router.post("/linkedin/post")
async def post_to_linkedin(
    post_data: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
):
    """
    Post to LinkedIn using stored access token.
    """
    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID not found in token")
    
    # Load access token
    token_result = supabase.table("linkedin_tokens").select("access_token, expires_at").eq("user_id", user_id).limit(1).execute()
    if not token_result.data:
        raise HTTPException(status_code=404, detail="LinkedIn tokens not found. Please connect your LinkedIn account first.")
    
    token_data = token_result.data[0]
    access_token = token_data.get("access_token")
    expires_at = token_data.get("expires_at")
    
    if not access_token:
        raise HTTPException(status_code=500, detail="Access token not found in database")
    
    if expires_at and datetime.utcnow().timestamp() > expires_at:
        raise HTTPException(status_code=401, detail="LinkedIn token expired. Please reconnect your LinkedIn account.")
    
    # Extract post content
    text = post_data.get("text")
    if not text:
        raise HTTPException(status_code=400, detail="Post text is required")
    
    owner_urn = post_data.get("owner_urn")
    # Prefer image_url (public URL for MCP); image_path may be data URL for display only
    image_url_or_data = post_data.get("image_url") or post_data.get("image_path")
    # Post to LinkedIn via social automation service
    social_service = await get_social_automation_service()
    agent_response = await social_service.post_to_linkedin(
        post_text=text,
        access_token=access_token,
        image_url_or_data=image_url_or_data,
        owner_urn=owner_urn
    )

    # Store post details in Supabase linkedin_posts when successful
    if isinstance(agent_response, dict) and agent_response.get("success") and agent_response.get("post_id"):
        post_urn = agent_response.get("post_id")
        if post_urn and str(post_urn).strip().startswith("urn:li:"):
            try:
                supabase.table("linkedin_posts").insert({
                    "user_id": user_id,
                    "post_urn": post_urn.strip(),
                }).execute()
            except Exception:
                pass

    return agent_response
