import logging
from fastapi import APIRouter, Depends, HTTPException, status,Path
from models.event_models import Event
from models.event_models import AgendaItem
from models.event_models import Speaker
from pydantic import BaseModel
from services.auth_services import verify_token, get_admin_by_email
from fastapi.security import OAuth2PasswordBearer
from typing import Optional, List
from datetime import datetime
import pytz
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

    # Use secure admin verification function
    admin_data = get_admin_by_email(email)
    if not admin_data:
        raise HTTPException(status_code=403, detail="Not authorized - admin access required")

    admin_id = admin_data["id"]
    logging.info(f"Event creation authorized for admin: {admin_data['name']}")

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
            "poster_url": event.poster_url,
            "admin_id": admin_id,
        }).execute()

        if not event_response.data:
            raise HTTPException(status_code=500, detail="Failed to create event")

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

        logging.info(f"Event created successfully: {event_id}")
        return {
            "message": "Event created successfully", 
            "event_id": event_id,
            "admin": {
                "id": admin_data["id"],
                "name": admin_data["name"],
                "email": admin_data["email"]
            }
        }

    except Exception as e:
        logging.error(f"Error creating event: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@event_router.put("/events/update/{event_id}")
def update_event(event_id: str,event: Event,token_data: dict = Depends(verify_token)):
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

    admin_resp = supabase.table("admins").select("*").eq("email", email).limit(1).execute()
    if not admin_resp.data:
        raise HTTPException(status_code=403, detail="Admin privileges required")

    admin_id = admin_resp.data[0]["id"]

    # Verify event exists
    event_resp = supabase.table("events").select("*").eq("id", str(event_id)).limit(1).execute()
    if not event_resp.data:
        raise HTTPException(status_code=404, detail="Event not found or unauthorized")

    try:
        old_event_data = event_resp.data[0]
        old_date_time = old_event_data.get("date_time")
        
        update_data = {
            k: (v.isoformat() if isinstance(v, datetime) else v)
            for k, v in event.dict(exclude_unset=True).items()
            if k not in ["speakers", "agenda"]
        }
        
        # Check if date_time is being updated
        new_date_time = update_data.get("date_time")
        date_time_changed = False
        if new_date_time and old_date_time and new_date_time != old_date_time:
            date_time_changed = True
            logging.info(f"Event {event_id} date_time changed from {old_date_time} to {new_date_time}")

        # Update main event data
        supabase.table("events").update(update_data).eq("id", str(event_id)).execute()
        
        # Reschedule reminder jobs if event time changed
        if date_time_changed:
            try:
                from services.event_email_scheduler import reschedule_reminders_for_event
                import asyncio
                
                # Parse new date_time
                new_event_datetime = datetime.fromisoformat(new_date_time.replace('Z', '+00:00'))
                
                # Reschedule all reminder jobs for this event
                rescheduled = asyncio.run(reschedule_reminders_for_event(str(event_id), new_event_datetime))
                logging.info(f"Rescheduled {rescheduled} reminder jobs for event {event_id}")
            except Exception as reschedule_error:
                logging.warning(f"Failed to reschedule reminders for event {event_id}: {reschedule_error}")
                # Don't fail event update if rescheduling fails

        # Only update speakers and agenda if they are provided
        if hasattr(event, 'speakers') and event.speakers is not None:
            # Remove existing speakers
            supabase.table("event_speakers").delete().eq("event_id", str(event_id)).execute()
            
            # Insert new speakers (only if there are any)
            if event.speakers:
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
                supabase.table("event_speakers").insert(speakers_payload).execute()

        if hasattr(event, 'agenda') and event.agenda is not None:
            # Remove existing agenda items
            supabase.table("event_agenda").delete().eq("event_id", str(event_id)).execute()
            
            # Insert new agenda items (only if there are any)
            if event.agenda:
                agenda_payload = [
                    {
                        "duration": a.duration,
                        "topic": a.topic,
                        "description": a.description,
                        "event_id": str(event_id)
                    } for a in event.agenda
                ]
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
    Get all events with their speakers and agenda items.
    Only admins can access this endpoint.
    """
    try:
        email = token_data.get("email")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token payload")

        # Verify admin access
        admin_data = get_admin_by_email(email)
        if not admin_data:
            raise HTTPException(status_code=403, detail="Not authorized - admin access required")

        logging.info(f"Fetching all events for admin: {admin_data['name']}")

        # Get all events first (limit to recent events for better performance)
        events_response = supabase.table("events").select("*").order("date_time", desc=True).limit(50).execute()
        
        if not events_response.data:
            return {"events": []}

        # Get event IDs for efficient filtering
        event_ids = [event["id"] for event in events_response.data]
        
        # Get speakers for only these events
        speakers_response = supabase.table("event_speakers").select("*").in_("event_id", event_ids).execute()
        speakers = speakers_response.data if speakers_response.data else []
        
        # Get agenda items for only these events
        agenda_response = supabase.table("event_agenda").select("*").in_("event_id", event_ids).execute()
        agenda_items = agenda_response.data if agenda_response.data else []
        
        # Group speakers and agenda by event_id for efficient lookup
        speakers_by_event = {}
        for speaker in speakers:
            event_id = speaker["event_id"]
            if event_id not in speakers_by_event:
                speakers_by_event[event_id] = []
            speakers_by_event[event_id].append(speaker)
        
        agenda_by_event = {}
        for agenda_item in agenda_items:
            event_id = agenda_item["event_id"]
            if event_id not in agenda_by_event:
                agenda_by_event[event_id] = []
            agenda_by_event[event_id].append(agenda_item)
        
        # Combine events with their speakers and agenda
        events = []
        for event in events_response.data:
            event_id = event["id"]
            event["speakers"] = speakers_by_event.get(event_id, [])
            event["agenda"] = agenda_by_event.get(event_id, [])
            events.append(event)

        logging.info(f"Successfully fetched {len(events)} events")
        return {"events": events}

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error fetching all events: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching events: {e}")

@event_router.get("/events/public")
def get_public_events():
    """
    Get all events with their speakers and agenda items for public access.
    No authentication required.
    """
    try:
        logging.info("Fetching public events")

        # Get all events first (limit to recent events for better performance)
        events_response = supabase.table("events").select("*").order("date_time", desc=True).limit(50).execute()
        
        if not events_response.data:
            return {"events": []}

        # Get event IDs for efficient filtering
        event_ids = [event["id"] for event in events_response.data]
        
        # Get speakers for only these events
        speakers_response = supabase.table("event_speakers").select("*").in_("event_id", event_ids).execute()
        speakers = speakers_response.data if speakers_response.data else []
        
        # Get agenda items for only these events
        agenda_response = supabase.table("event_agenda").select("*").in_("event_id", event_ids).execute()
        agenda_items = agenda_response.data if agenda_response.data else []
        
        # Group speakers and agenda by event_id for efficient lookup
        speakers_by_event = {}
        for speaker in speakers:
            event_id = speaker["event_id"]
            if event_id not in speakers_by_event:
                speakers_by_event[event_id] = []
            speakers_by_event[event_id].append(speaker)
        
        agenda_by_event = {}
        for agenda_item in agenda_items:
            event_id = agenda_item["event_id"]
            if event_id not in agenda_by_event:
                agenda_by_event[event_id] = []
            agenda_by_event[event_id].append(agenda_item)
        
        # Combine events with their speakers and agenda
        events = []
        for event in events_response.data:
            event_id = event["id"]
            event["speakers"] = speakers_by_event.get(event_id, [])
            event["agenda"] = agenda_by_event.get(event_id, [])
            events.append(event)

        logging.info(f"Successfully fetched {len(events)} public events")
        return {"events": events}

    except Exception as e:
        logging.error(f"Error fetching public events: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching events: {e}")


@event_router.get("/events/upcoming")
def get_upcoming_events(limit: int = 10, tz: str = "America/Los_Angeles"):
    """
    Public endpoint: return future events only, ascending by date.
    """
    try:
        logging.info("Fetching upcoming events")
        try:
            timezone = pytz.timezone(tz)
        except Exception:
            timezone = pytz.UTC
        now_iso = datetime.now(timezone).isoformat()

        events_resp = (
            supabase
            .table("events")
            .select("*")
            .gte("date_time", now_iso)
            .order("date_time", desc=False)
            .limit(limit)
            .execute()
        )
        return {"events": events_resp.data or []}
    except Exception as e:
        logging.error(f"Error fetching upcoming: {e}")
        raise HTTPException(status_code=500, detail="Error fetching upcoming events")


def _is_valid_uuid(val: str) -> bool:
    try:
        uuid_obj = UUID(val, version=4)  # You can specify version if needed
        return str(uuid_obj) == val
    except (ValueError, AttributeError, TypeError):
        return False
        
@event_router.get("/events/{event_id}")
def get_event_by_id(event_id: str):
    """
    Retrieve a specific event by ID including speakers and agenda items.
    """
    try:
        # Get the event
        event_response = supabase.table("events").select("*").eq("id", event_id).execute()
        if not event_response.data:
            raise HTTPException(status_code=404, detail="Event not found")
        
        event = event_response.data[0]
        
        # Get speakers for this event
        speaker_response = supabase.table("event_speakers").select("*").eq("event_id", event_id).execute()
        event["speakers"] = speaker_response.data if speaker_response.data else []
        
        # Get agenda for this event
        agenda_response = supabase.table("event_agenda").select("*").eq("event_id", event_id).execute()
        event["agenda"] = agenda_response.data if agenda_response.data else []
        
        return event

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error fetching event {event_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching event: {e}")

