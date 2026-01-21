from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import RedirectResponse
from supabase import create_client, Client
from services.mcp_service import get_current_user, call_mcp_tool
from config.settings import SUPABASE_URL, SUPABASE_SERVICE_KEY, LINKEDIN_REDIRECT_URI, FRONTEND_BASE_URL
from datetime import datetime, timedelta
import logging
import secrets
import os
import tempfile
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
        
        logger.info(f"LinkedIn connect initiated for user: {email}")
        
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
        except Exception as e:
            # If table doesn't exist, we'll handle it in callback
            logger.warning(f"Could not store state mapping: {e}")
        
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
            logger.info(f"Returning LinkedIn OAuth URL as JSON for user: {email}")
            return {"url": login_url, "state": state}
        
        logger.info(f"Redirecting to LinkedIn OAuth URL for user: {email}")
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
        
        logger.info(f"LinkedIn OAuth callback received with state: {state[:8]}...")
        
        # Retrieve user_id from state mapping
        user_id = None
        try:
            state_result = supabase.table("oauth_states").select("user_id").eq("state", state).limit(1).execute()
            if state_result.data and len(state_result.data) > 0:
                user_id = state_result.data[0].get("user_id")
                # Delete used state (one-time use)
                supabase.table("oauth_states").delete().eq("state", state).execute()
        except Exception as e:
            logger.warning(f"Could not retrieve user_id from state mapping: {e}")
        
        if not user_id:
            logger.error(f"Could not retrieve user_id for state: {state[:8]}...")
            raise HTTPException(
                status_code=400,
                detail="Invalid or expired state parameter. Please try connecting again."
            )
        
        logger.info(f"LinkedIn OAuth callback for user_id: {user_id}, exchanging code for tokens")
        
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
        
        logger.info(f"LinkedIn tokens received, storing in Supabase for user_id: {user_id}")
        
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
            
            logger.info(f"LinkedIn tokens stored successfully for user_id: {user_id}")
            
        except Exception as e:
            logger.error(f"Error storing LinkedIn tokens in Supabase: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to store LinkedIn tokens: {str(e)}"
            )
        
        # Redirect to frontend Admin page social media section
        redirect_url = f"{FRONTEND_BASE_URL}/admin?linkedin=connected"
        
        logger.info(f"Redirecting to frontend: {redirect_url}")
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
        
        logger.info(f"Checking LinkedIn status for user: {email}")
        
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
    Loads access_token from Supabase and calls MCP post_to_linkedin.
    """
    try:
        user_id = current_user.get("user_id")
        email = current_user.get("email")
        
        if not user_id:
            raise HTTPException(
                status_code=400,
                detail="User ID not found in token"
            )
        
        logger.info(f"Posting to LinkedIn for user: {email}")
        
        # Load access_token from Supabase
        token_result = supabase.table("linkedin_tokens").select("access_token, refresh_token, expires_at").eq("user_id", user_id).limit(1).execute()
        
        if not token_result.data or len(token_result.data) == 0:
            raise HTTPException(
                status_code=404,
                detail="LinkedIn tokens not found. Please connect your LinkedIn account first."
            )
        
        token_data = token_result.data[0]
        access_token = token_data.get("access_token")
        expires_at = token_data.get("expires_at")
        
        # Check if token is expired (optional - you might want to refresh)
        if expires_at and datetime.utcnow().timestamp() > expires_at:
            logger.warning(f"LinkedIn token expired for user: {email}")
            raise HTTPException(
                status_code=401,
                detail="LinkedIn token expired. Please reconnect your LinkedIn account."
            )
        
        if not access_token:
            raise HTTPException(
                status_code=500,
                detail="Access token not found in database"
            )
        
        # Extract post content from request
        text = post_data.get("text")
        if not text:
            raise HTTPException(
                status_code=400,
                detail="Post text is required"
            )
        
        owner_urn = post_data.get("owner_urn")  # Optional
        image_url_or_data = post_data.get("image_path") or post_data.get("image_url")  # Optional - can be URL or data URL
        
        # Handle image: download from URL/data URL to temporary file if provided
        image_path = None
        temp_file = None
        if image_url_or_data:
            try:
                # Check if it's a data URL (base64)
                if image_url_or_data.startswith("data:image/"):
                    # Extract base64 data
                    header, encoded = image_url_or_data.split(",", 1)
                    # Determine file extension from MIME type
                    mime_type = header.split(":")[1].split(";")[0]
                    ext = ".png"  # default
                    if "jpeg" in mime_type or "jpg" in mime_type:
                        ext = ".jpg"
                    elif "png" in mime_type:
                        ext = ".png"
                    
                    # Decode base64 and save to temp file
                    image_data = base64.b64decode(encoded)
                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
                    temp_file.write(image_data)
                    temp_file.close()
                    image_path = temp_file.name
                    logger.info(f"Downloaded image from data URL to temp file: {image_path}")
                    
                elif image_url_or_data.startswith("http://") or image_url_or_data.startswith("https://"):
                    # Download from URL
                    response = requests.get(image_url_or_data, timeout=30)
                    response.raise_for_status()
                    
                    # Determine file extension from URL or Content-Type
                    content_type = response.headers.get("Content-Type", "image/png")
                    ext = ".png"  # default
                    if "jpeg" in content_type or "jpg" in content_type:
                        ext = ".jpg"
                    elif "png" in content_type:
                        ext = ".png"
                    
                    # Save to temp file
                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
                    temp_file.write(response.content)
                    temp_file.close()
                    image_path = temp_file.name
                    logger.info(f"Downloaded image from URL to temp file: {image_path}")
                    
                elif os.path.exists(image_url_or_data):
                    # It's already a local file path
                    image_path = image_url_or_data
                    logger.info(f"Using existing local file path: {image_path}")
                else:
                    logger.warning(f"Image path provided but not in recognized format: {image_url_or_data[:100]}")
                    
            except Exception as e:
                logger.error(f"Error processing image: {e}")
                # Continue without image if there's an error
                image_path = None
        
        # Call MCP server to post to LinkedIn
        result = None
        try:
            result = await call_mcp_tool(
                "post_to_linkedin",
                {
                    "text": text,
                    "access_token": access_token,
                    "owner_urn": owner_urn,
                    "image_path": image_path
                }
            )
            
            # Log the full result structure for debugging
            logger.info(f"LinkedIn MCP tool response type: {type(result)}")
            if isinstance(result, dict):
                logger.info(f"LinkedIn MCP tool response keys: {list(result.keys())}")
                logger.info(f"LinkedIn MCP tool response: {json.dumps(result, indent=2, default=str)}")
            elif isinstance(result, list):
                logger.info(f"LinkedIn MCP tool response (list length {len(result)}): {json.dumps(result, indent=2, default=str)}")
            else:
                logger.info(f"LinkedIn MCP tool response: {str(result)}")
            
        finally:
            # Clean up temporary file if created
            if temp_file and os.path.exists(temp_file.name):
                try:
                    os.unlink(temp_file.name)
                    logger.info(f"Cleaned up temporary image file: {temp_file.name}")
                except Exception as e:
                    logger.warning(f"Failed to delete temporary file {temp_file.name}: {e}")
        
        # Extract post URN from the result
        post_urn = None
        
        if result:
            # Handle different result formats
            actual_result = result
            
            # If result is a list, get the first item
            if isinstance(result, list) and len(result) > 0:
                actual_result = result[0]
                logger.info(f"Result is a list, using first item: {type(actual_result)}")
            
            # Check if result is wrapped in a "result" key (from MCP service)
            if isinstance(actual_result, dict):
                # If result has a "result" key, use that (common MCP pattern)
                if "result" in actual_result:
                    unwrapped = actual_result.get("result")
                    # If it's a string, try to parse it as JSON
                    if isinstance(unwrapped, str):
                        try:
                            unwrapped = json.loads(unwrapped)
                        except:
                            pass
                    actual_result = unwrapped
                # Also check if result itself is the data we need
                elif "id" in actual_result or "ugcPostId" in actual_result or "shareId" in actual_result:
                    # Keep actual_result as is
                    pass
            
            # Now extract from the actual result
            if isinstance(actual_result, dict):
                # Try multiple possible fields for post URN
                post_urn = (
                    actual_result.get("id") or 
                    actual_result.get("ugcPostId") or 
                    actual_result.get("shareId") or
                    actual_result.get("ugcPost") or
                    actual_result.get("post_id") or
                    actual_result.get("postId")
                )
                
                # Also check nested structures
                if not post_urn:
                    # Check if there's a nested result
                    nested_result = actual_result.get("result")
                    if isinstance(nested_result, dict):
                        post_urn = (
                            nested_result.get("id") or 
                            nested_result.get("ugcPostId") or 
                            nested_result.get("shareId")
                        )
                
                # Search for URN patterns in the entire dict structure
                if not post_urn:
                    result_str = json.dumps(actual_result, default=str)
                    # Look for URN patterns
                    ugc_matches = re.findall(r'urn:li:ugcPost:(\d+)', result_str)
                    if ugc_matches:
                        post_urn = f"urn:li:ugcPost:{ugc_matches[0]}"
                    else:
                        share_matches = re.findall(r'urn:li:share:(\d+)', result_str)
                        if share_matches:
                            post_urn = f"urn:li:share:{share_matches[0]}"
            
            # If result is a string, try to parse it
            elif isinstance(actual_result, str):
                try:
                    parsed = json.loads(actual_result)
                    if isinstance(parsed, dict):
                        post_urn = (
                            parsed.get("id") or 
                            parsed.get("ugcPostId") or 
                            parsed.get("shareId")
                        )
                except:
                    # If not JSON, search for URN patterns in the string
                    ugc_matches = re.findall(r'urn:li:ugcPost:(\d+)', actual_result)
                    if ugc_matches:
                        post_urn = f"urn:li:ugcPost:{ugc_matches[0]}"
                    else:
                        share_matches = re.findall(r'urn:li:share:(\d+)', actual_result)
                        if share_matches:
                            post_urn = f"urn:li:share:{share_matches[0]}"
        
        if not post_urn:
            logger.warning(f"LinkedIn post response did not contain a post URN.")
            logger.warning(f"Full result structure: {json.dumps(result, indent=2, default=str) if isinstance(result, (dict, list)) else str(result)}")
            logger.error("LinkedIn post was created but no post URN was returned. Cannot save to database.")
        else:
            logger.info(f"Extracted post_urn: {post_urn}")
            # Store post details in Supabase
            try:
                # Ensure user_id is properly formatted as UUID
                # Validate UUID format, then use as string (Supabase Python client handles UUID conversion)
                try:
                    # Validate and format UUID
                    if isinstance(user_id, str):
                        user_id_uuid = uuid_lib.UUID(user_id)
                    else:
                        user_id_uuid = uuid_lib.UUID(str(user_id))
                    user_id_str = str(user_id_uuid)
                    logger.info(f"Validated user_id UUID: {user_id_str}")
                except (ValueError, AttributeError, TypeError) as e:
                    logger.error(f"Invalid UUID format for user_id: {user_id} (type: {type(user_id)}), error: {e}")
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid user ID format: {user_id}"
                    )
                
                # Ensure post_urn is a string (TEXT type in Supabase)
                post_urn_str = str(post_urn)
                if not post_urn_str or not post_urn_str.strip():
                    raise HTTPException(
                        status_code=400,
                        detail="Post URN cannot be empty"
                    )
                
                post_record = {
                    "user_id": user_id_str,  # UUID as string (Supabase Python client converts to UUID type)
                    "post_urn": post_urn_str,  # TEXT type
                    "posted_at": datetime.utcnow().isoformat(),  # TIMESTAMPTZ (ISO format string)
                    "created_at": datetime.utcnow().isoformat()  # TIMESTAMPTZ (ISO format string)
                }
                
                logger.info(f"Attempting to insert post record into linkedin_posts table:")
                logger.info(f"  user_id: {user_id_str} (type: {type(user_id_str)})")
                logger.info(f"  post_urn: {post_urn} (type: {type(post_urn)})")
                logger.info(f"  posted_at: {post_record['posted_at']}")
                logger.info(f"  created_at: {post_record['created_at']}")
                
                insert_result = supabase.table("linkedin_posts").insert(post_record).execute()
                
                logger.info(f"Insert result type: {type(insert_result)}")
                logger.info(f"Insert result: {insert_result}")
                
                if hasattr(insert_result, 'data') and insert_result.data:
                    logger.info(f"LinkedIn post details stored in database for user: {email}, post_urn: {post_urn}")
                    logger.info(f"Inserted record: {insert_result.data}")
                elif hasattr(insert_result, 'data'):
                    logger.warning(f"Insert returned no data. Response object: {insert_result}")
                    logger.warning(f"Response attributes: {dir(insert_result)}")
                else:
                    logger.warning(f"Insert result doesn't have 'data' attribute. Full result: {insert_result}")
                    
            except Exception as e:
                # Log detailed error information
                logger.error(f"Error storing LinkedIn post details in database: {e}", exc_info=True)
                logger.error(f"Exception type: {type(e)}")
                logger.error(f"Exception args: {e.args}")
                logger.error(f"Post record that failed: user_id={user_id} (type: {type(user_id)}), post_urn={post_urn} (type: {type(post_urn)})")
                logger.warning(f"Post was published to LinkedIn (URN: {post_urn}) but details were not saved to database")
        
        if post_urn:
            logger.info(f"Successfully posted to LinkedIn for user: {email}, post_urn: {post_urn}")
        else:
            logger.warning(f"Successfully posted to LinkedIn for user: {email}, but post_urn was not extracted")
        
        return {
            "success": True,
            "message": "Post published to LinkedIn successfully",
            "post_urn": post_urn or "N/A",
            "result": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error posting to LinkedIn: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to post to LinkedIn: {str(e)}"
        )
