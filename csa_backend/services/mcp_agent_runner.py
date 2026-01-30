"""
MCP Agent Runner Service
Opens an MCP session, loads MCP tools, creates a LangChain agent, and invokes it.
Returns the raw agent response without any parsing or modification.
"""

from fastapi import HTTPException
from langchain_mcp_adapters.client import MultiServerMCPClient  # type: ignore
from langchain_mcp_adapters.tools import load_mcp_tools  # type: ignore
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent  # type: ignore
from langchain_core.messages import ToolMessage  # type: ignore
from config.settings import MCP_SERVER_URL, OPENAI_API_KEY, OPENAI_MODEL
import logging

logger = logging.getLogger(__name__)


async def run_mcp_agent(messages: list):
    """
    Open an MCP session, load MCP tools, create a LangChain agent, and invoke it.
    
    Args:
        messages: List of LangChain messages to pass to the agent
        
    Returns:
        Raw agent response without any parsing or modification
    """
    try:
        mcp_client = MultiServerMCPClient(
            connections={
                "mcp_server": {
                    "transport": "http",
                    "url": MCP_SERVER_URL
                }
            }
        )
        logger.info("MCP client initialized successfully")
        
        # Initialize LangChain LLM
        if not OPENAI_API_KEY:
            logger.error("OPENAI_API_KEY not configured")
            raise ValueError("OPENAI_API_KEY not configured")
        llm = ChatOpenAI(
            model=OPENAI_MODEL,
            temperature=0.7,
            api_key=OPENAI_API_KEY
        )
        async with mcp_client.session("mcp_server") as session:
            tools = await load_mcp_tools(session)
            agent = create_agent(llm, tools)
            result = await agent.ainvoke({"messages": messages})
            # Extract content and tool results from agent response
            text = ""
            tool_results = []
            if isinstance(result, dict) and "messages" in result:
                msgs = result["messages"]
                for msg in msgs:
                    if isinstance(msg, ToolMessage):
                        content = getattr(msg, "content", None)
                        if content is not None:
                            tool_results.append(content if isinstance(content, str) else str(content))
                if msgs:
                    last_msg = msgs[-1]
                    text = getattr(last_msg, "content", "") or ""
            elif hasattr(result, "content"):
                text = result.content or ""
            else:
                text = str(result or "")
            
            text = text.strip()
            
            # Unwrap optional code fences to keep the response clean
            if text.startswith("```"):
                if "```json" in text:
                    text = text.split("```json", 1)[1].rsplit("```", 1)[0].strip()
                else:
                    text = text.strip("` \n")
            
            return {"content": text, "tool_results": tool_results}
            
    except Exception as e:
        logger.error(f"Error running MCP agent: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to run MCP agent: {str(e)}"
        )
