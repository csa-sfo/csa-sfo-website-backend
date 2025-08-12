import logging
from fastapi import APIRouter, Depends, HTTPException, status,Path
from models.event_models import Event
from models.event_models import AgendaItem
from models.event_models import Speaker
from services.auth_services import verify_token
from fastapi.security import OAuth2PasswordBearer
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from supabase import create_client, Client
import os

# Initialize router
event_router = APIRouter()

# OAuth2 scheme for token extraction
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

# Supabase setup
SUPABASE_URL = os.getenv("CSA_SUPABASE_URL")
SUPABASE_KEY = os.getenv("CSA_SUPABASE_SERVICE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


@event_router.post("/create")
async def create_event(event: Event, token: str = Depends(oauth2_scheme)):
    # Here you would validate token and save event in DB
    if token != "validtoken":  # Simplified check
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return {"msg": "Event created", "event": event}

@event_router.post("/events/create")
def create_event(event: Event, token_data: dict = Depends(verify_token)):
    """
    Create a new event with related speakers and agenda items.
    Only admins can perform this action.
    """
    logging.info("Attempting to create event")

    email = token_data.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    # Validate admin
    admin_check = supabase.table("admins").select("*").eq("email", email).limit(1).execute()
    if not admin_check.data or admin_check.data[0]["role"] != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    admin_id = admin_check.data[0]["id"]

    try:
        # Insert event into database
        event_response = supabase.table("events").insert({
            "title": event.title,
            "date_time": event.date_time.isoformat(),
            "slug": event.slug,
            "location": event.location,
            "checkins":event.checkins,
            "excerpt": event.excerpt,
            "description": event.description,
            "tags": event.tags,
            "capacity": event.capacity,
            "attendees": event.attendees,
            "reg_url": event.reg_url,
            "map_url": event.map_url,
            "admin_id": admin_id,
        }).execute()

        event_id = event_response.data[0]["id"]

        # Insert speakers
        speaker_payload = [
            {
                "name": speaker.name,
                "role": speaker.role,
                "company": speaker.company,
                "image_url": speaker.image_url,
                "about": speaker.about,
                "event_id": event_id
            }
            for speaker in event.speakers
        ]
        if speaker_payload:
            supabase.table("event_speakers").insert(speaker_payload).execute()

        # Insert agenda items
        agenda_item_payload = [
            {
                "duration": item.duration,
                "topic": item.topic,
                "description": item.description,
                "event_id": event_id
            }
            for item in event.agenda
        ]
        if agenda_item_payload:
            supabase.table("event_agenda").insert(agenda_item_payload).execute()

        logging.info(f"Event created: {event_id}")
        return {"message": "Event created successfully", "event_id": event_id}

    except Exception as e:
        logging.error(f"Error creating event: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@event_router.put("/events/update/{event_id}")
def update_event(event_id: UUID,event: Event,token_data: dict = Depends(verify_token)):
    """
    Update an existing event and replace its related speakers and agenda.
    Only the admin who created the event can update it.
    """
    logging.info(f"Updating event {event_id}")
    if not _is_valid_uuid(event_id):
        raise HTTPException(status_code=400, detail="Invalid event ID format")
    logging.info(f"Updating event {event_id}")
    email = token_data.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    admin_resp = supabase.table("admnins").select("*").eq("email", email).limit(1).execute()
    if not admin_resp.data or admin_resp.data[0]["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")

    admin_id = admin_resp.data[0]["id"]

    # Verify event exists
    event_resp = supabase.table("events").select("*").eq("id", str(event_id)).eq("admin_id", admin_id).limit(1).execute()
    if not event_resp.data:
        raise HTTPException(status_code=404, detail="Event not found or unauthorized")

    try:
        update_data = {
            k: (v.isoformat() if isinstance(v, datetime) else v)
            for k, v in event.dict(exclude_unset=True).items()
            if k not in ["speakers", "agenda"]
        }

        # Update main event data
        supabase.table("events").update(update_data).eq("id", str(event_id)).execute()

        # Remove existing related data
        supabase.table("event_speakers").delete().eq("event_id", str(event_id)).execute()
        supabase.table("event_agenda").delete().eq("event_id", str(event_id)).execute()

        # Re-insert new speakers
        speakers_payload = [
            {
                "name": s.name,
                "role": s.role,
                "company": s.company,
                "image_url": s.image_url,
                "about": s.about,
                "event_id": str(event_id)
            } for s in event.speakers
        ]
        if speakers_payload:
            supabase.table("event_speakers").insert(speakers_payload).execute()

        # Re-insert new agenda items
        agenda_payload = [
            {
                "duration": a.duration,
                "topic": a.topic,
                "description": a.description,
                "event_id": str(event_id)
            } for a in event.agenda
        ]
        if agenda_payload:
            supabase.table("event_agenda").insert(agenda_payload).execute()

        logging.info(f"Event {event_id} updated")
        return {"message": "Event updated successfully", "event_id": str(event_id)}

    except Exception as e:
        logging.error(f"Error updating event {event_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update event")




@event_router.delete("/events/delete/{event_id}")
def delete_event(event_id: str, token_data: dict = Depends(verify_token)):
    """
    Delete an event by its ID.
    Only admins can delete events.
    """
    if not _is_valid_uuid(event_id):
        raise HTTPException(status_code=400, detail="Invalid event ID format")

    email = token_data.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    try:
        admin_resp = supabase.table("admins").select("*").eq("email", email).limit(1).execute()
        if not admin_resp.data:
            raise HTTPException(status_code=403, detail="Admin privileges required")
    except Exception as e:
        logging.error(f"Error checking admin: {e}")
        raise HTTPException(status_code=500, detail="Admin check failed")

    event_resp = supabase.table("events").select("id").eq("id", event_id).limit(1).execute()
    if not event_resp.data:
        raise HTTPException(status_code=404, detail="Event not found")

    delete_resp = supabase.table("events").delete().eq("id", event_id).execute()
    if not delete_resp.data:
        logging.warning(f"Failed to delete event: {event_id}")
        raise HTTPException(status_code=500, detail="Failed to delete event")

    logging.info(f"Event deleted: {event_id}")
    return {"message": "Event deleted successfully"}

@event_router.get("/events/all")
def get_all_events(token_data: dict = Depends(verify_token)):
    """
    Retrieve all events including their associated speakers and agenda items.
    """
    try:
        events_response = supabase.table("events").select("*").execute()
        if not events_response.data:
            return {"events": []}

        events = events_response.data

        for event in events:
            event_id = event["id"]

            speaker_response = supabase.table("event_speakers").select("*").eq("event_id", event_id).execute()
            agenda_response = supabase.table("event_agenda").select("*").eq("event_id", event_id).execute()

            event["speakers"] = speaker_response.data if speaker_response.data else []
            event["agenda"] = agenda_response.data if agenda_response.data else []

        return {"events": events}

    except Exception as e:
        logging.error(f"Error fetching events: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching events: {e}")
    
def _is_valid_uuid(val: str) -> bool:
    try:
        uuid_obj = UUID(val, version=4)  # You can specify version if needed
        return str(uuid_obj) == val
    except (ValueError, AttributeError, TypeError):
        return False