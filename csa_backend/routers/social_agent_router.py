from fastapi import APIRouter, HTTPException, Depends
from supabase import create_client, Client
from services.mcp_service import get_current_user, call_mcp_tool
from config.settings import SUPABASE_URL, SUPABASE_SERVICE_KEY
from datetime import datetime
import os
import logging
import re
from dotenv import load_dotenv
from typing import Dict, Any

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize router
social_agent_router = APIRouter()

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


@social_agent_router.post("/social-agent/generate-event-content")
async def generate_event_content(
    request_data: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
):
    """
    Generate text content for an event using Gemini MCP tool.
    Fetches event details from Supabase and generates engaging social media content with hashtags.
    """
    try:
        user_id = current_user.get("user_id")
        email = current_user.get("email")
        
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
        
        logger.info(f"Generating content for event {event_id} for user: {email}")
        
        # Fetch event details from Supabase
        try:
            event_response = supabase.table("events").select("*").eq("id", event_id).limit(1).execute()
            if not event_response.data or len(event_response.data) == 0:
                raise HTTPException(
                    status_code=404,
                    detail="Event not found"
                )
            
            event = event_response.data[0]
            
            # Get speakers for this event
            speaker_response = supabase.table("event_speakers").select("*").eq("event_id", event_id).execute()
            speakers = speaker_response.data if speaker_response.data else []
            
            # Build comprehensive topic/prompt for content generation
            event_title = event.get("title", "Event")
            event_location = event.get("location", "")
            event_date = event.get("date_time", "")
            event_description = event.get("description") or event.get("excerpt", "")
            
            # Format date nicely
            formatted_date = ""
            if event_date:
                try:
                    from datetime import datetime
                    date_obj = datetime.fromisoformat(event_date.replace('Z', '+00:00'))
                    formatted_date = date_obj.strftime("%B %d, %Y at %I:%M %p")
                except:
                    formatted_date = event_date
            
            # Build topic description with event details
            topic_parts = [
                f"Create a single, engaging LinkedIn post caption for an event: {event_title}",
            ]
            if formatted_date:
                topic_parts.append(f"Date and Time: {formatted_date}")
            if event_location:
                topic_parts.append(f"Location: {event_location}")
            if event_description:
                topic_parts.append(f"Event Description: {event_description}")
            if speakers:
                speaker_names = ", ".join([s.get("name", "") for s in speakers[:5]])
                topic_parts.append(f"Featured Speakers: {speaker_names}")
            
            topic_parts.append("Generate ONLY ONE LinkedIn post caption in Markdown format. Use proper formatting with line breaks, paragraphs, bullet points, and bold text where appropriate. Include relevant hashtags for cloud security, cybersecurity, technology events, and professional networking. Make it engaging, professional, and suitable for LinkedIn. Format the content with Markdown syntax (use ** for bold, * for italic, - or * for bullet points, empty lines for paragraph breaks). Do not provide multiple options or alternatives - provide only one complete post caption in Markdown format.")
            
            content_topic = ". ".join(topic_parts)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching event details: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to fetch event details: {str(e)}"
            )
        
        # Call MCP server to generate content using Gemini
        try:
            result = await call_mcp_tool(
                "generate_content",
                {
                    "topic": content_topic
                }
            )
            
            # Extract generated content from result
            generated_text = result.get("result") or str(result)
            
            # Extract hashtags from the generated content (look for #hashtag patterns)
            hashtag_pattern = r'#(\w+)'
            found_hashtags = re.findall(hashtag_pattern, generated_text, re.IGNORECASE)
            
            # Also include some default/trending hashtags for cloud security events
            default_hashtags = ['CloudSecurity', 'CyberSecurity', 'InfoSec', 'TechEvent', 'CSA', 'Networking', 'TechCommunity']
            
            # Combine found hashtags with defaults, remove duplicates, and limit to 10
            all_hashtags = list(dict.fromkeys([h.capitalize() for h in found_hashtags] + default_hashtags))[:10]
            
            logger.info(f"Successfully generated content for event {event_id}")
            return {
                "success": True,
                "message": "Content generated successfully",
                "content": generated_text,
                "hashtags": all_hashtags,
                "event": {
                    "id": event_id,
                    "title": event_title,
                    "location": event_location,
                    "date_time": event_date
                }
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error generating content with Gemini MCP: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to generate content: {str(e)}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in generate_event_content: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate event content: {str(e)}"
        )


@social_agent_router.post("/social-agent/generate-event-image")
async def generate_event_image(
    request_data: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
):
    """
    Generate an image for an event using Gemini MCP tool.
    Fetches event details from Supabase and generates an image based on the event.
    """
    try:
        user_id = current_user.get("user_id")
        email = current_user.get("email")
        
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
        
        logger.info(f"Generating image for event {event_id} for user: {email}")
        
        # Fetch event details from Supabase
        try:
            event_response = supabase.table("events").select("*").eq("id", event_id).limit(1).execute()
            if not event_response.data or len(event_response.data) == 0:
                raise HTTPException(
                    status_code=404,
                    detail="Event not found"
                )
            
            event = event_response.data[0]
            
            # Get speakers for this event
            speaker_response = supabase.table("event_speakers").select("*").eq("event_id", event_id).execute()
            speakers = speaker_response.data if speaker_response.data else []
            
            # Build prompt for image generation based on event details
            event_title = event.get("title", "Event")
            event_location = event.get("location", "")
            event_date = event.get("date_time", "")
            event_description = event.get("description") or event.get("excerpt", "")
            
            # Create a descriptive prompt for the image
            prompt_parts = [
                f"A professional event promotion image for: {event_title}",
            ]
            if event_location:
                prompt_parts.append(f"Location: {event_location}")
            if event_description:
                # Use first 100 chars of description
                desc_short = event_description[:100].replace("\n", " ").strip()
                prompt_parts.append(f"About: {desc_short}")
            if speakers:
                # Only include speaker names (not images) in the prompt
                # Filter to only speakers with names - do not include any speaker images
                valid_speakers = [s for s in speakers[:3] if s.get("name")]
                if valid_speakers:
                    speaker_names = ", ".join([s.get("name", "") for s in valid_speakers])
                    prompt_parts.append(f"Featuring speakers (text only): {speaker_names}")
            
            prompt_parts.append("Style: Modern, professional, clean design with technology/cloud security theme. Suitable for social media promotion.")
            prompt_parts.append("CRITICAL: Do not generate, create, or include any images, illustrations, photos, or visual representations of people, speakers, or faces. Speaker names must appear as plain text only. Use only abstract graphics, icons, shapes, and text elements. No person images allowed.")
            
            image_prompt = ". ".join(prompt_parts)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error fetching event details: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to fetch event details: {str(e)}"
            )
        
        # Call MCP server to generate image using Gemini
        try:
            result = await call_mcp_tool(
                "generate_image",
                {
                    "prompt": image_prompt
                }
            )
            
            # Extract image path from result
            # The MCP tool returns a file path, which might be in different formats
            image_path = result.get("result") or result.get("path") or str(result)
            
            # Read the image file and convert to base64 for frontend display
            import base64
            image_data_url = None
            if image_path and os.path.exists(image_path):
                try:
                    with open(image_path, "rb") as image_file:
                        image_data = image_file.read()
                        image_base64 = base64.b64encode(image_data).decode("utf-8")
                        # Determine MIME type from file extension
                        if image_path.lower().endswith('.png'):
                            mime_type = 'image/png'
                        elif image_path.lower().endswith('.jpg') or image_path.lower().endswith('.jpeg'):
                            mime_type = 'image/jpeg'
                        else:
                            mime_type = 'image/png'  # default
                        image_data_url = f"data:{mime_type};base64,{image_base64}"
                except Exception as e:
                    logger.warning(f"Failed to read image file {image_path}: {e}")
                    image_data_url = None
            
            logger.info(f"Successfully generated image for event {event_id}: {image_path}")
            return {
                "success": True,
                "message": "Image generated successfully",
                "image_path": image_data_url or image_path,  # Return base64 data URL if available, else path
                "event": {
                    "id": event_id,
                    "title": event_title,
                    "location": event_location,
                    "date_time": event_date
                }
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error generating image with Gemini MCP: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to generate image: {str(e)}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in generate_event_image: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate event image: {str(e)}"
        )
