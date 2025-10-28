from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Dict, Any

import pytz

from db.supabase import get_supabase_client, safe_supabase_operation


async def fetch_upcoming_events(limit: int = 3, timezone: str = "America/Los_Angeles") -> List[Dict[str, Any]]:
    """Return upcoming events (date_time >= now in the given timezone), ascending by date.

    Each event contains the raw columns from the `events` table. Consumers can
    decide how to format for display.
    """
    try:
        tz = pytz.timezone(timezone)
        now = datetime.now(tz)
        now_iso = now.isoformat()

        supabase = get_supabase_client()
        op = lambda: (
            supabase
            .table("events")
            .select("*")
            .gte("date_time", now_iso)
            .order("date_time", desc=False)
            .limit(limit)
            .execute()
        )
        resp = await safe_supabase_operation(op, "Failed to fetch upcoming events")
        return resp.data or []
    except Exception as exc:
        logging.exception("fetch_upcoming_events failed: %s", exc)
        return []


def format_upcoming_events_for_prompt(events: List[Dict[str, Any]], timezone: str = "America/Los_Angeles") -> str:
    """Format a list of events into a compact, LLM-friendly bullet list.

    Example output:
    Upcoming Events (local time):
    - Oct 29, 2025 — Hackoween Horrors (San Francisco) — Register: https://...
    """
    if not events:
        return ""

    try:
        tz = pytz.timezone(timezone)
    except Exception:
        tz = pytz.UTC

    lines: List[str] = ["Upcoming Events (local time):"]
    for ev in events:
        title = (ev.get("title") or "").strip()
        location = (ev.get("location") or "").strip()
        reg_url = (ev.get("reg_url") or "").strip()

        # Parse event date_time in a tolerant way
        dt_raw = ev.get("date_time")
        when_str = ""
        try:
            # Assume stored as RFC3339/ISO-8601; try fromisoformat fallback
            dt = datetime.fromisoformat(str(dt_raw).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = tz.localize(dt)
            else:
                dt = dt.astimezone(tz)
            when_str = dt.strftime("%b %d, %Y — %I:%M %p %Z")
        except Exception:
            when_str = str(dt_raw)

        pieces = [when_str]
        if title:
            pieces.append(f"— {title}")
        if location:
            pieces.append(f"({location})")
        line = " ".join(pieces)
        if reg_url:
            line += f" — Register: {reg_url}"
        lines.append(f"- {line}")

    return "\n".join(lines)


