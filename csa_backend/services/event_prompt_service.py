"""
Event Prompt Service
Service for fetching event/speaker data from Supabase and converting to prompt context format.
Handles event formatting, date conversion, and speaker text formatting.
"""

from datetime import datetime
from typing import Dict, Any, List

from supabase import create_client
from config.settings import SUPABASE_URL, SUPABASE_SERVICE_KEY

# Lazy-initialized Supabase client for event/speaker fetching
_supabase = None


def _get_supabase():
    global _supabase
    if _supabase is None:
        _supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    return _supabase


def event_id_to_prompt_context(event_id: str) -> Dict[str, Any]:
    """
    Fetch event and speakers from Supabase by event_id and return prompt context.

    Args:
        event_id: Event UUID (string).

    Returns:
        Dictionary with keys: event_title, event_description, event_date, event_location,
        event_tags, event_reg_url, event_checkins, speakers (formatted text).

    Raises:
        ValueError: If event is not found.
    """
    event_id = str(event_id).strip()
    supabase = _get_supabase()

    event_response = supabase.table("events").select("*").eq("id", event_id).limit(1).execute()
    if not event_response.data or len(event_response.data) == 0:
        raise ValueError("Event not found")

    event = event_response.data[0]
    event_id_from_db = event.get("id")
    speaker_response = supabase.table("event_speakers").select("*").eq("event_id", event_id_from_db).execute()
    speakers = speaker_response.data if speaker_response.data else []
    event["speakers"] = speakers

    return event_to_prompt_context(event, speakers)


def event_to_prompt_context(event: Dict[str, Any], speakers: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Convert event data from Supabase to prompt context format.

    Event fields used: title, description, date_time, location, tags, reg_url, checkins.
    Speaker fields used: name, role, company, image_url.

    Args:
        event: Event dictionary from Supabase (title, description, date_time, location, tags, reg_url, checkins).
        speakers: Optional list of speaker dictionaries (name, role, company, image_url).

    Returns:
        Dictionary with keys: event_title, event_description, event_date, event_location,
        event_tags, event_reg_url, event_checkins, speakers (formatted text).
    """
    # Format date from date_time
    event_date_raw = event.get("date_time") or event.get("date")
    formatted_date = ""
    if event_date_raw:
        try:
            date_obj = datetime.fromisoformat(str(event_date_raw).replace("Z", "+00:00"))
            formatted_date = date_obj.strftime("%B %d, %Y at %I:%M %p")
        except Exception:
            formatted_date = str(event_date_raw)

    # Format speakers: name, role, company, image_url (prefer passed list, fallback to event.speakers)
    speakers_list = speakers if (speakers is not None and len(speakers) > 0) else event.get("speakers") or []
    speaker_lines = []
    for s in speakers_list:
        if not isinstance(s, dict):
            continue
        # Support both common keys (name/role/company) and alternate DB keys (e.g. speaker_name)
        name = s.get("name") or s.get("speaker_name") or "Speaker"
        role = s.get("role") or s.get("speaker_role") or ""
        company = s.get("company") or s.get("speaker_company") or ""
        image_url = s.get("image_url") or ""
        parts = [name]
        if role:
            parts.append(f"({role})")
        if company:
            parts.append(f"from {company}")
        line = " ".join(parts)
        if image_url:
            line += f" | Image: {image_url}"
        speaker_lines.append("- " + line)
    speakers_text = "\n".join(speaker_lines) if speaker_lines else "No speakers listed"

    tags_value = event.get("tags")
    event_tags_str = ", ".join(tags_value) if isinstance(tags_value, list) else (tags_value or "")

    context = {
        "event_title": event.get("title") or "Event",
        "event_description": event.get("description") or "",
        "event_date": formatted_date,
        "event_location": event.get("location") or "",
        "event_tags": event_tags_str,
        "event_reg_url": event.get("reg_url") or "",
        "event_checkins": event.get("checkins") or "",
        "speakers": speakers_text,
    }
    return context
