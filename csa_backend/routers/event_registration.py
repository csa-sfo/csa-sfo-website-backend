import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from supabase import create_client, Client
import os
from typing import Optional

# Initialize router
event_registration_router = APIRouter()

# Supabase setup - will be created in functions
def get_supabase_client():
    """Get Supabase client with environment variables"""
    supabase_url = os.getenv("CSA_SUPABASE_URL")
    supabase_key = os.getenv("CSA_SUPABASE_SERVICE_KEY")
    if not supabase_url or not supabase_key:
        raise Exception("Supabase credentials not found")
    return create_client(supabase_url, supabase_key)

# Event Registration Models
class EventRegistrationRequest(BaseModel):
    user_id: str
    event_id: str

class EventRegistrationResponse(BaseModel):
    id: str
    user_id: str
    event_id: str
    message: str

@event_registration_router.post("/event-registrations", response_model=EventRegistrationResponse)
async def create_event_registration(registration: EventRegistrationRequest):
    """
    Register a user for an event.
    Creates a new event registration record in the database.
    """
    logging.info(f"Attempting to register user {registration.user_id} for event {registration.event_id}")
    
    try:
        supabase = get_supabase_client()
        
        # Validate user exists
        user_response = supabase.table("users").select("id, email").eq("id", registration.user_id).limit(1).execute()
        if not user_response.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Validate event exists
        event_response = supabase.table("events").select("id, title, capacity, attendees").eq("id", registration.event_id).limit(1).execute()
        if not event_response.data:
            raise HTTPException(status_code=404, detail="Event not found")
        
        event_data = event_response.data[0]
        
        # Check if user is already registered
        existing_registration = supabase.table("event_registrations").select("id").eq(
            "user_id", registration.user_id
        ).eq("event_id", registration.event_id).limit(1).execute()
        
        if existing_registration.data:
            raise HTTPException(status_code=400, detail="User already registered for this event")
        
        # Check if event is at capacity
        if event_data["attendees"] >= event_data["capacity"]:
            raise HTTPException(status_code=400, detail="Event is at full capacity")
        
        # Create new registration
        registration_response = supabase.table("event_registrations").insert({
            "user_id": registration.user_id,
            "event_id": registration.event_id
        }).execute()
        
        if not registration_response.data:
            raise HTTPException(status_code=500, detail="Failed to create registration")
        
        # Update event attendees count
        new_attendees = event_data["attendees"] + 1
        supabase.table("events").update({
            "attendees": new_attendees
        }).eq("id", registration.event_id).execute()
        
        registration_id = registration_response.data[0]["id"]
        
        logging.info(f"Registration created: {registration_id}")
        return EventRegistrationResponse(
            id=registration_id,
            user_id=registration.user_id,
            event_id=registration.event_id,
            message="Registration successful"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error creating registration: {e}")
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")

