"""
Social Automation Service
High-level service for social media automation including content generation, image generation,
and LinkedIn posting using LangChain MCP.
Handles prompt template loading, context formatting, and passes payloads to mcp_agent_runner.
"""

from fastapi import HTTPException
from services.mcp_agent_runner import run_mcp_agent
from services.event_prompt_service import event_id_to_prompt_context
from langchain_core.messages import HumanMessage  # type: ignore
from typing import Any
import logging
import os
import re
import base64
import requests
import json

logger = logging.getLogger(__name__)


class SocialAutomationService:
    """Service for social media automation including content/image generation and LinkedIn posting using AI-based tool selection."""
    
    def __init__(self):
        """Initialize the social automation service."""
        pass
    
    async def generate_content(self, event_id: str) -> Any:
        """
        Generate content for an event using AI-based tool selection.

        Args:
            event_id: Event UUID. Event and speakers are fetched inside the service.

        Returns:
            Any: Raw agent response (content string). Router/frontend interpret the response.

        Raises:
            ValueError: If event is not found (caller may map to HTTP 404).
        """
        try:
            context = event_id_to_prompt_context(event_id)
            # Load prompt template
            prompt_path = os.path.join(
                os.path.dirname(__file__),
                "..",
                "prompts",
                "social_automation",
                "content_generation_prompt.txt"
            )
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt_template = f.read()
            formatted_prompt = prompt_template.format(**context)
            
            # Create messages for the agent
            messages = [HumanMessage(content=formatted_prompt)]
            try:
                response = await run_mcp_agent(messages)
            except Exception as agent_error:
                logger.error(f"Error in run_mcp_agent call: {agent_error}", exc_info=True)
                raise
            if isinstance(response, dict) and "content" in response:
                return response["content"]
            return response
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error generating content: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to generate content: {str(e)}"
            )
    
    async def generate_image(self, event_id: str) -> Any:
        """
        Generate an image for an event using AI-based tool selection.

        Args:
            event_id: Event UUID. Event and speakers are fetched inside the service.

        Returns:
            Any: Dict with image_data_url and image_url, or raises.

        Raises:
            ValueError: If event is not found (caller may map to HTTP 404).
        """
        try:
            context = event_id_to_prompt_context(event_id)
            # Load prompt template
            prompt_path = os.path.join(
                os.path.dirname(__file__),
                "..",
                "prompts",
                "social_automation",
                "image_generation_prompt.txt"
            )
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt_template = f.read()
            formatted_prompt = prompt_template.format(**context)
            messages = [HumanMessage(content=formatted_prompt)]
            try:
                response = await run_mcp_agent(messages)
            except Exception as agent_error:
                logger.error(f"Error in run_mcp_agent call: {agent_error}", exc_info=True)
                raise
            
            # Extract image URL from MCP tool results (Gemini generate_image returns URL)
            image_url = None
            if isinstance(response, dict):
                tool_results = response.get("tool_results") or []
                for result in tool_results:
                    s = (result if isinstance(result, str) else str(result)).strip()
                    if s.startswith("https://"):
                        image_url = s
                        break
                if not image_url and response.get("content"):
                    # Fallback: try to parse URL from final content (response is always https://)
                    content = response["content"]
                    match = re.search(r"https://[^\s\)\]\"']+", content)
                    if match:
                        image_url = match.group(0).rstrip(".,;:)")
            
            if not image_url:
                return {"image_data_url": None, "image_url": None}
            
            # Fetch image from URL and convert to base64 for frontend display
            try:
                resp = requests.get(image_url, timeout=30)
                resp.raise_for_status()
                image_base64 = base64.b64encode(resp.content).decode("utf-8")
                content_type = resp.headers.get("content-type", "image/png").split(";")[0].strip()
                if content_type not in ("image/png", "image/jpeg", "image/gif", "image/webp"):
                    content_type = "image/png"
                image_data_url = f"data:{content_type};base64,{image_base64}"
                return {"image_data_url": image_data_url, "image_url": image_url}
            except Exception as fetch_err:
                logger.error(f"Failed to fetch image from URL '{image_url}': {fetch_err}", exc_info=True)
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to fetch generated image from URL: {str(fetch_err)}"
                )
        except ValueError as ve:
            if "not found" in str(ve).lower():
                raise
            logger.error(f"Error generating image: {ve}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(ve))
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error generating image: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to generate image: {str(e)}"
            )

    async def post_to_linkedin(self, post_text: str, access_token: str, image_url_or_data: str = None, owner_urn: str = None) -> Any:
        """
        Post to LinkedIn using AI-based tool selection.
        
        Args:
            post_text: Text content to post
            access_token: LinkedIn access token
            image_url_or_data: Optional image URL (http/https) or data URL (data:image/...)
            owner_urn: Optional LinkedIn owner URN
            
        Returns:
            Any: Raw agent response with no structure guarantees. The service layer
                 makes no assumptions about the response format. The router or frontend
                 is responsible for interpreting and handling the response structure.
        """
        try:
            # Load prompt template
            prompt_path = os.path.join(
                os.path.dirname(__file__),
                "..",
                "prompts",
                "social_automation",
                "posting_prompt.txt"
            )
            
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt_template = f.read()
            
            # Use only public image URL for MCP (do not pass base64 to the LLM)
            image_url = None
            if image_url_or_data and isinstance(image_url_or_data, str) and image_url_or_data.strip().startswith("https://"):
                image_url = image_url_or_data.strip()
            # Build payload with keys matching MCP tool post_to_linkedin(text, access_token, owner_urn, image_url)
            payload = {
                "text": post_text,
                "access_token": access_token
            }
            if image_url:
                payload["image_url"] = image_url
            if owner_urn:
                payload["owner_urn"] = owner_urn
            
            # Convert payload to JSON string
            payload_json = json.dumps(payload)
            
            # Format prompt with JSON payload
            user_message = prompt_template.format(payload=payload_json)
            
            # Create messages for the agent
            messages = [
                HumanMessage(content=user_message)
            ]
            
            # Invoke agent
            response = await run_mcp_agent(messages)
            
            # Normalize response for frontend: expect { success, post_id, error }
            out = {"success": False, "post_id": None, "error": None}
            content = None
            if isinstance(response, dict) and "content" in response:
                content = response.get("content") or ""
                tool_results = response.get("tool_results") or []
                # Prefer parsing LLM's final JSON from content
                if content:
                    raw = content.strip()
                    if raw.startswith("```"):
                        raw = raw.split("```json", 1)[-1].split("```", 1)[0].strip() if "```" in raw else raw.strip("` \n")
                    try:
                        parsed = json.loads(raw)
                        if isinstance(parsed, dict):
                            out["success"] = parsed.get("success", False)
                            out["post_id"] = parsed.get("post_id")
                            out["error"] = parsed.get("error")
                    except json.JSONDecodeError:
                        pass
                # If content didn't parse, check tool_results for post_to_linkedin result
                if not out["post_id"] and tool_results:
                    for tr in tool_results:
                        try:
                            if isinstance(tr, str) and (tr.startswith("{") or "post_id" in tr):
                                p = json.loads(tr) if isinstance(tr, str) else tr
                                if isinstance(p, dict) and (p.get("post_id") or p.get("id")):
                                    out["success"] = True
                                    out["post_id"] = p.get("post_id") or p.get("id")
                                    break
                        except (json.JSONDecodeError, TypeError):
                            continue
            if not out["post_id"] and content and ("success" in content.lower() or "urn:li:" in content):
                out["success"] = True
            out["message"] = out.get("error")  # frontend checks data.message on failure
            return out
                
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error posting to LinkedIn: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to post to LinkedIn: {str(e)}"
            )


# Global service instance
_social_automation_service = None


async def get_social_automation_service() -> SocialAutomationService:
    """Get or create the global social automation service instance."""
    global _social_automation_service
    if _social_automation_service is None:
        _social_automation_service = SocialAutomationService()
    return _social_automation_service
