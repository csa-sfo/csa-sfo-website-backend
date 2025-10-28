
import logging
import asyncio
import time
from typing import Dict, Any

try:    
    from app.config.settings import OPENAI_API_KEY
except:
    from config.settings import OPENAI_API_KEY

try:
    from agents import Agent, Runner, set_default_openai_key
    from agents.mcp import MCPServerStdio
except Exception as _e:  # pragma: no cover
    raise ImportError("agents package is required. Install with: pip install agents")



def get_urls():
    urls = [
        "https://csasfo.com/",
        "https://csasfo.com/about",
        "https://csasfo.com/events",
        "https://csasfo.com/archive",
        "https://csasfo.com/get-involved",
        "https://csasfo.com/contact",
        "https://csasfo.com/sponsorship",



    ]
    return urls 



# Scrape URL and convert to markdown with deep crawl for dynamic content
async def scrapped_website_content(url: str, *, max_event_pages: int = 12, max_total_pages: int = 18) -> str:
    """
    Use the Playwright MCP server (spawned via stdio) with OpenAI Agent to deeply crawl `url` and
    extract human-visible content, including dynamically loaded sections. Specifically ensure events
    on the homepage and events pages are fully expanded and followed into detail pages.

    Returns consolidated markdown followed by a machine-readable JSON block of extracted events.
    """
    # Configure OpenAI for the agent SDK
    set_default_openai_key(OPENAI_API_KEY)

    # Rich, deterministic instruction for deeper crawling and structured extraction
    lines = []
    lines.append("You are a precise web extraction agent using a Playwright MCP browser.")
    lines.append("Task: Given a start URL, perform a DEEP CRAWL within the same origin to fully collect readable content,")
    lines.append("with special focus on Events. Follow these steps carefully:\n")
    lines.append("1) Navigation & Stability:")
    lines.append("   - Navigate to the URL. Wait for 'networkidle' and DOM to stabilize.")
    lines.append("   - Perform progressive auto-scroll to the bottom (20 small steps), with short waits between steps,")
    lines.append("     until no new content is added for 2 iterations.")
    lines.append("   - Click visible buttons/links likely to reveal content: 'Load more', 'Show more', 'More', 'View more',")
    lines.append("     'See all', 'Upcoming', 'Past events', 'Expand', etc. Wait briefly after each click.\n")
    lines.append("2) Event Discovery & Following:")
    lines.append("   - On pages listing events, extract each event card details when present: title, date, time, location,")
    lines.append("     price/fee, registration link, speakers, description, and the event detail URL.")
    lines.append(f"   - Collect distinct event detail URLs within the same origin. Visit up to {max_event_pages} of them, and")
    lines.append(f"     never exceed a total of {max_total_pages} pages including the start page.")
    lines.append("   - For each visited event detail page: wait for stability, auto-scroll, expand hidden sections, and extract")
    lines.append("     the same fields plus the main body content.\n")
    lines.append("3) Output Format:")
    lines.append("   - Produce readable Markdown. Segment content by page with headings like '## Page: <URL>'.")
    lines.append("   - Include links as Markdown links.")
    lines.append("   - After the Markdown, output a JSON block delimited exactly as follows:")
    lines.append("     ---START-EVENTS-JSON---")
    lines.append("     {\"events\": [ {fields...}, ... ] }")
    lines.append("     ---END-EVENTS-JSON---")
    lines.append("   - The JSON array should contain a consolidated, deduplicated list of all events seen. Each event object")
    lines.append("     should include: title, url, date, time, location, price, registration_url, speakers (array of names),")
    lines.append("     description (short), and page_type ('list'|'detail'). Leave unknown fields as empty strings.\n")
    lines.append("4) Constraints: Stay within the same origin. Never login. Be resilient to lazy-loading. Use reasonable waits (<= 3s)")
    lines.append("   between actions. If selectors are not found, gracefully continue.")
    instruction = "\n".join(lines)

    # Retry MCP server startup up to ~120s total (12 attempts x ~10s each)
    last_err = None
    for _ in range(12):
        try:
            async with MCPServerStdio(
                name="Playwright-mcp",
                params={"command": "npx", "args": ["-y", "@playwright/mcp@latest"]},
            ) as server:
                agent = Agent(
                    name="Playwright-mcp",
                    model="gpt-4.1",
                    instructions=instruction,
                    mcp_servers=[server],
                )
                # Extend run timeout to 180s overall for deep crawl
                result = await asyncio.wait_for(Runner.run(agent, url), timeout=180)
                text = (result.final_output or "").strip()
                break
        except Exception as e:
            last_err = e
            await asyncio.sleep(10)
    else:
        raise last_err
    return text
