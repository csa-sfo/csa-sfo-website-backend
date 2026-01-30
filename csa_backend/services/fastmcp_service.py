"""
FastMCP Service
Shared utilities for interacting with MCP (Model Context Protocol) server via FastMCP.
"""

from fastapi import HTTPException, Depends
from services.auth_services import verify_token
from config.settings import MCP_SERVER_URL
import logging
import json

# Set up logging
logger = logging.getLogger(__name__)


# Dependency to get current user
def get_current_user(token_data: dict = Depends(verify_token)) -> dict:
    """
    Get current user from JWT token.
    Returns user information including user_id and email.
    
    Args:
        token_data: Token data from verify_token dependency
        
    Returns:
        dict: User information including user_id and email
    """
    return token_data


# Helper function to call MCP server tools
async def call_mcp_tool(tool_name: str, arguments: dict) -> dict:
    """
    Call an MCP server tool via FastMCP Client.
    The MCP server must be running with HTTP transport on the configured URL.
    
    Args:
        tool_name: Name of the MCP tool to call
        arguments: Dictionary of arguments to pass to the tool
        
    Returns:
        dict: Result from the MCP tool call
        
    Raises:
        HTTPException: If FastMCP is not installed or if the tool call fails
    """
    try:
        # Import FastMCP Client to call tools properly
        try:
            from fastmcp import Client
        except ImportError:
            logger.error("fastmcp package not installed. Please install it: pip install fastmcp")
            raise HTTPException(
                status_code=500,
                detail="FastMCP client library not installed. Please install fastmcp package."
            )
        
        # Connect to MCP server using FastMCP Client
        # The URL should point to the MCP endpoint (typically /mcp for streamable HTTP)
        mcp_url = MCP_SERVER_URL
        client = Client(mcp_url)
        
        async with client:
            # Call the tool using the MCP protocol
            result = await client.call_tool(tool_name, arguments)
            
            # Extract the result from MCP response format
            # FastMCP returns CallToolResult with content array
            if result.content and len(result.content) > 0:
                # Get the first content block
                content_block = result.content[0]
                # Check if it's text content
                if hasattr(content_block, 'text'):
                    # Try to parse as JSON if possible, otherwise return as text
                    try:
                        return json.loads(content_block.text)
                    except (json.JSONDecodeError, AttributeError):
                        return {"result": content_block.text}
                # If it's already a dict/structured content
                elif isinstance(content_block, dict):
                    return content_block
                else:
                    # Fallback: convert to dict
                    return {"result": str(content_block)}
            else:
                # No content, return empty dict or error
                logger.warning(f"MCP tool {tool_name} returned no content")
                return {}
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calling MCP tool {tool_name}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error calling MCP tool: {str(e)}"
        )
