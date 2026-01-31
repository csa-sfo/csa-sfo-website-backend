from fastapi import APIRouter, HTTPException, Depends
from services.fastmcp_service import get_current_user
from services.social_automation_service import get_social_automation_service
import json
from dotenv import load_dotenv
from typing import Dict, Any

load_dotenv()

content_generation_router = APIRouter()


@content_generation_router.post("/social-agent/generate-event-content")
async def generate_event_content(
    request_data: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
):
    """
    Generate text content for an event using Gemini MCP tool.
    Fetches event details from Supabase and generates engaging social media content with hashtags.
    """
    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=400,
            detail="User ID not found in token"
        )
    
    # Extract event_id from request
    event_id = request_data.get("event_id")
    if not event_id:
        raise HTTPException(
            status_code=400,
            detail="Event ID is required"
        )
    event_id = str(event_id).strip()

    social_service = await get_social_automation_service()
    try:
        agent_response = await social_service.generate_content(event_id)
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail="Event not found")
        raise HTTPException(status_code=400, detail=str(e))
    
    # Parse JSON response from agent
    try:
        # Agent returns a JSON string, parse it
        if isinstance(agent_response, str):
            parsed = json.loads(agent_response)
        else:
            parsed = agent_response
        
        # Extract content field
        content = parsed.get("content", "") if isinstance(parsed, dict) else str(parsed)
        
        return {"content": content}
    except json.JSONDecodeError:
        return {"content": str(agent_response) if agent_response else ""}
    except Exception:
        return {"content": str(agent_response) if agent_response else ""}


@content_generation_router.post("/social-agent/generate-event-image")
async def generate_event_image(
    request_data: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
):
    """
    Generate an image for an event using Gemini MCP tool.
    Fetches event details from Supabase and generates an image based on the event.
    """
    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=400,
            detail="User ID not found in token"
        )
    
    # Extract event_id from request
    event_id = request_data.get("event_id")
    if not event_id:
        raise HTTPException(
            status_code=400,
            detail="Event ID is required"
        )
    event_id = str(event_id).strip()

    social_service = await get_social_automation_service()
    try:
        agent_response = await social_service.generate_image(event_id)
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail="Event not found")
        raise HTTPException(status_code=400, detail=str(e))
    
    if isinstance(agent_response, dict):
        image_data_url = agent_response.get("image_data_url")
        image_url = agent_response.get("image_url")
        if image_data_url:
            return {"image_path": image_data_url, "image_url": image_url or ""}
    return {"image_path": "", "image_url": ""}
