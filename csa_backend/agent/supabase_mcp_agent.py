import asyncio
import logging
import os

try:
    from app.config.settings import OPENAI_API_KEY, SUPABASE_ACCESS_TOKEN, SUPABASE_URL
except Exception:  # pragma: no cover
    from config.settings import OPENAI_API_KEY, SUPABASE_ACCESS_TOKEN, SUPABASE_URL

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain.agents import create_agent
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI


SYSTEM_PROMPT = (
    "You are a Chat Bot that answers all questions provided from the user using Supabase MCP. "
    "You will not edit or delete any data in Supabase. "
    "Use project ganqwjbdeivsmyekvojt to answer any questions except related to payments. "
    "All event information is present in public.events table and other event tables. "
    "Keep it short and brief. Answer all questions with PST time zone. "
    "The site home page is https://csasfo.com/. Don't post URLs that don't have home page."
)

FEW_SHOT = (
    "User Prompt: What is the next event?\n"
    "Assistant: The next upcoming event is the CSA San Francisco Chapter Meeting on January 28, 2026, "
    "at 5:30 PM PST. It will take place at Blackhawk Network, 6220 Stoneridge Mall Rd, Pleasanton, CA 94588.\n\n"
    "User Prompt: Who are the speakers?\n"
    "Assistant: For the upcoming CSA San Francisco Chapter Meeting on January 28, 2026, the speakers include "
    "Sudesh Gadewar (Keynote, Blackhawk Network) and Christopher Moy (Speaker, FBI).\n"
)

SCHEMA_HINT = (
    "Table hints:\n"
    "- public.events: id (uuid), title (text), description (text), date_time (timestamptz), location (text), reg_url (text), map_url (text), poster_url (text), attendees (int), updated_at (timestamptz).\n"
    "- public.event_speakers: id (uuid), event_id (uuid), name (text), role (text), company (text), about (text), image_url (text).\n"
    "- public.event_agenda: id (uuid), event_id (uuid), topic (text), description (text), duration (text).\n"
    "Use date_time for scheduling, not start_time; use title instead of name in events."
)

EVENT_KEYWORDS = (
    "event",
    "meeting",
    "speaker",
    "speakers",
    "agenda",
    "where",
    "when",
    "time",
    "location",
    "register",
    "registration",
    "tickets",
    "ticket",
    "rsvp",
    "capacity",
    "raffle",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _derive_project_id(url: str | None) -> str | None:
    """Extract project ref from a Supabase URL like https://<ref>.supabase.co."""
    if not url:
        return None
    try:
        host = url.split("://", 1)[-1]
        sub = host.split(".", 1)[0]
        return sub or None
    except Exception:
        return None


SUPABASE_PROJECT_ID = (
    os.getenv("CSA_SUPABASE_PROJECT_ID")
    or _derive_project_id(SUPABASE_URL)
    or "ganqwjbdeivsmyekvojt"
)


def is_event_query(text: str) -> bool:
    """Lightweight keyword gate to decide if we should route to Supabase MCP."""
    normalized = (text or "").lower()
    return any(keyword in normalized for keyword in EVENT_KEYWORDS)


async def run_supabase_mcp_agent(user_message: str, timeout: int = 45) -> str:
    """Answer event questions via the Supabase MCP server with read-only queries, using LangChain MCP tools."""
    if not SUPABASE_ACCESS_TOKEN:
        raise RuntimeError("SUPABASE_ACCESS_TOKEN is not configured for Supabase MCP.")

    instructions = "\n".join(
        [
            SYSTEM_PROMPT,
            "Use the Supabase MCP server to run ONLY one read-only (SELECT) query against "
            f"project `{SUPABASE_PROJECT_ID}`.",
            "Prefer the public.events, public.event_speakers, public.event_agenda, and related tables.",
            "When asked about topics/agenda, read from public.event_agenda.topic/description joined on event_id for the upcoming event (date_time > now, earliest first). Do not invent topics.",
            "Always return concise plain text (no code fences, no SQL), and convert times to America/Los_Angeles (PST/PDT).",
            "If data is missing, say so briefly instead of guessing.",
            "Do not ask the user to choose a project; assume the project ref above is already set.",
            "Respond in a single, friendly, human-readable sentence or two for the general public. Avoid technical or SQL terminology.",
            SCHEMA_HINT,
            FEW_SHOT,
        ]
    )

    env_vars = {
        "SUPABASE_ACCESS_TOKEN": SUPABASE_ACCESS_TOKEN,
        "SUPABASE_PROJECT_ID": SUPABASE_PROJECT_ID,
        "SUPABASE_PROJECT_REF": SUPABASE_PROJECT_ID,
    }
    if SUPABASE_URL:
        env_vars["SUPABASE_URL"] = SUPABASE_URL

    server_params = StdioServerParameters(
        command="npx",
        args=["-y", "@supabase/mcp-server-supabase@latest"],
        env=env_vars,
    )

    last_err: Exception | None = None
    for attempt in range(3):
        try:
            logging.info(
                "Supabase MCP attempt %s: starting stdio_client with env vars project_id=%s url=%s",
                attempt + 1,
                SUPABASE_PROJECT_ID,
                SUPABASE_URL,
            )
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    logging.info("Supabase MCP attempt %s: initializing session", attempt + 1)
                    await session.initialize()
                    logging.info("Supabase MCP attempt %s: loading tools via load_mcp_tools", attempt + 1)
                    tools = await load_mcp_tools(session)

                    llm = ChatOpenAI(
                        api_key=OPENAI_API_KEY,
                        model="gpt-4.1-mini",
                        temperature=0.3,
                    )
                    agent = create_agent(llm, tools)

                    messages = [
                        SystemMessage(content=instructions),
                        HumanMessage(content=user_message),
                    ]

                    logging.info("Supabase MCP attempt %s: invoking agent", attempt + 1)
                    result = await asyncio.wait_for(
                        agent.ainvoke({"messages": messages}),
                        timeout=timeout,
                    )

                    # LangChain agents often return {"messages": [...]}
                    text = ""
                    if isinstance(result, dict) and "messages" in result:
                        msgs = result["messages"]
                        if msgs:
                            last_msg = msgs[-1]
                            text = getattr(last_msg, "content", "") or ""
                    elif hasattr(result, "content"):
                        text = result.content or ""
                    else:
                        text = str(result or "")

                    text = text.strip()

                    # Unwrap optional code fences to keep the response clean for the chat UI.
                    if text.startswith("```"):
                        if "```json" in text:
                            text = text.split("```json", 1)[1].rsplit("```", 1)[0].strip()
                        else:
                            text = text.strip("` \n")

                    return text
        except Exception as exc:  # pragma: no cover
            last_err = exc
            logging.warning(f"Supabase MCP attempt {attempt + 1} failed: {exc}", exc_info=True)
            await asyncio.sleep(2 * (attempt + 1))

    raise last_err or RuntimeError("Supabase MCP failed after retries.")


__all__ = ["run_supabase_mcp_agent", "is_event_query"]
