import json
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



async def parse_company_website_mcp(url: str) -> Dict[str, Any]:
    """
    Use the Playwright MCP server (spawned via stdio) together with OpenAI APIs
    to crawl `url` and return a JSON dict with the schema:

    {
      company,
      objective,
      headquarters: { address, city, state, country },
      offices: [{ address, city, state, country }],
      contact: { phone, primary_email, secondary_phone, secondary_email, linkedin, x, instagram, youtube, other[] },
      key_competencies: [{ service, summary, offerings[], certifications[] }],
      clients: [{ name, title, organization, comments }],
      employees: { total_count, employee_info: [{ name, competency, contact_info }] },
      meta_data: { ...any other important information }
    }

    """
    # Configure OpenAI for the agent SDK
    set_default_openai_key(OPENAI_API_KEY)

    # Strong instruction to return ONLY the requested JSON
    instruction = (
        "Crawl the website and extract everything about the company possible. "
        "Return ONLY a JSON object with EXACT keys and structure: "
        "{company, objective, headquarters{address,city,state,country}, offices[{address,city,state,country}], "
        "contact{phone,primary_email,secondary_phone,secondary_email,linkedin,x,instagram,youtube,other}, "
        "key_competencies[{service,summary,offerings,certifications}], clients[{name,title,organization,comments}], "
        "employees{total_count,employee_info[{name,competency,contact_info}]}, meta_data}."
    )

    async with MCPServerStdio(
        name="Playwright-mcp",
        params={"command": "npx", "args": ["-y", "@playwright/mcp@latest"]},
    ) as server:
        agent = Agent(
            name="Playwright-mcp",
            model="gpt-4o-mini",
            instructions=instruction,
            mcp_servers=[server],
        )
        result = await Runner.run(agent, url)
        text = (result.final_output or "").strip()
        if text.startswith("```"):
            if "```json" in text:
                text = text.split("```json", 1)[1].rsplit("```", 1)[0].strip()
            else:
                text = text.strip("`\n")
        return json.loads(text or "{}")


# Backward-compatible adapter returning a JSON string for existing callers
async def scrapped_website_content(url):
    data = await parse_company_website_mcp(url)
    return json.dumps(data)


__all__ = [
    "parse_company_website_mcp",
    "scrapped_website_content",
    "get_urls",
]
