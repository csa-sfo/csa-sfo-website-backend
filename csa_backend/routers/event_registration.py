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
        
        # Validate user exists in either users or admins table
        user_response = supabase.table("users").select("id, email").eq("id", registration.user_id).limit(1).execute()
        admin_response = supabase.table("admins").select("id, email").eq("id", registration.user_id).limit(1).execute()
        
        if not user_response.data and not admin_response.data:
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

@event_registration_router.get("/event-registrations/{user_id}")
async def get_user_registrations(user_id: str):
    """
    Get all event registrations for a specific user.
    """
    logging.info(f"Fetching registrations for user {user_id}")
    
    try:
        supabase = get_supabase_client()
        
        # Validate user exists in either users or admins table
        user_response = supabase.table("users").select("id").eq("id", user_id).limit(1).execute()
        admin_response = supabase.table("admins").select("id").eq("id", user_id).limit(1).execute()
        
        if not user_response.data and not admin_response.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Get user's registrations with event details
        registrations_response = supabase.table("event_registrations").select(
            "id, event_id, events(title, date_time, location, slug)"
        ).eq("user_id", user_id).execute()
        
        return {
            "registrations": registrations_response.data if registrations_response.data else []
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error fetching registrations: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch registrations: {str(e)}")

@event_registration_router.delete("/event-registrations/{registration_id}")
async def cancel_event_registration(registration_id: str):
    """
    Cancel an event registration.
    """
    logging.info(f"Cancelling registration {registration_id}")
    
    try:
        supabase = get_supabase_client()
        
        # Get registration details
        registration_response = supabase.table("event_registrations").select(
            "id, user_id, event_id, events(attendees)"
        ).eq("id", registration_id).limit(1).execute()
        
        if not registration_response.data:
            raise HTTPException(status_code=404, detail="Registration not found")
        
        registration_data = registration_response.data[0]
        event_id = registration_data["event_id"]
        current_attendees = registration_data["events"]["attendees"]
        
        # Delete registration
        delete_response = supabase.table("event_registrations").delete().eq("id", registration_id).execute()
        
        if not delete_response.data:
            raise HTTPException(status_code=500, detail="Failed to cancel registration")
        
        # Update event attendees count
        new_attendees = max(0, current_attendees - 1)
        supabase.table("events").update({
            "attendees": new_attendees
        }).eq("id", event_id).execute()
        
        logging.info(f"Registration {registration_id} cancelled")
        return {"message": "Registration cancelled successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error cancelling registration: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel registration: {str(e)}")

@event_registration_router.post("/simple-registration")
async def simple_event_registration(registration: EventRegistrationRequest):
    """
    Test endpoint for event registration without authentication
    """
    logging.info(f"Test registration: user {registration.user_id} for event {registration.event_id}")
    
    try:
        supabase = get_supabase_client()
        
        # Get event details first
        event_response = supabase.table("events").select("id, attendees, capacity").eq("id", registration.event_id).limit(1).execute()
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
        
        logging.info(f"Test registration created: {registration_id}")
        return {
            "id": registration_id,
            "user_id": registration.user_id,
            "event_id": registration.event_id,
            "message": "Test registration successful"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error in test registration: {e}")
        raise HTTPException(status_code=500, detail=f"Test registration failed: {str(e)}")

@event_registration_router.get("/event-attendees/{event_id}")
async def get_event_attendees(event_id: str):
    """
    Get the current attendees count for a specific event.
    """
    try:
        supabase = get_supabase_client()
        
        # Get event details
        event_response = supabase.table("events").select("id, attendees, capacity").eq("id", event_id).execute()
        if not event_response.data:
            raise HTTPException(status_code=404, detail="Event not found")
        
        event = event_response.data[0]
        
        # Return the attendees count from events table (which is kept up-to-date by registrations)
        return {
            "event_id": event_id,
            "attendees": event["attendees"],
            "capacity": event["capacity"],
            "spots_left": event["capacity"] - event["attendees"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting event attendees: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting attendees: {e}")

@event_registration_router.get("/event-registered-users/{event_id}")
async def get_event_registered_users(event_id: str):
    """
    Get all registered users for a specific event with their details.
    """
    try:
        supabase = get_supabase_client()
        
        # Get event details to verify it exists
        event_response = supabase.table("events").select("id, title").eq("id", event_id).execute()
        if not event_response.data:
            raise HTTPException(status_code=404, detail="Event not found")
        
        # Get all registrations for this event
        registrations_response = supabase.table("event_registrations").select("user_id, updated_at").eq("event_id", event_id).execute()
        
        if not registrations_response.data:
            return {
                "event_id": event_id,
                "registered_users": [],
                "count": 0
            }
        
        # Get user details for each registration
        user_ids = [reg["user_id"] for reg in registrations_response.data]
        
        # Fetch users from users table
        users_response = supabase.table("users").select("id, name, email, company_name, role, avatar_url").in_("id", user_ids).execute()
        users = users_response.data if users_response.data else []
        
        # Also check admins table in case any admins registered
        admins_response = supabase.table("admins").select("id, name, email").in_("id", user_ids).execute()
        admins = admins_response.data if admins_response.data else []
        
        # Combine users and admins, adding a type field
        all_users = []
        for user in users:
            user["user_type"] = "user"
            all_users.append(user)
        
        for admin in admins:
            admin["user_type"] = "admin"
            admin["company_name"] = "CSA Admin"
            admin["role"] = "Administrator"
            admin["avatar_url"] = None
            all_users.append(admin)
        
        # Create a map of user details by ID
        user_map = {user["id"]: user for user in all_users}
        
        # Combine registration data with user details
        registered_users = []
        for reg in registrations_response.data:
            user_id = reg["user_id"]
            if user_id in user_map:
                user_data = user_map[user_id].copy()
                user_data["registered_at"] = reg.get("updated_at", "")
                registered_users.append(user_data)
        
        return {
            "event_id": event_id,
            "registered_users": registered_users,
            "count": len(registered_users)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting registered users for event: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting registered users: {e}")

@event_registration_router.get("/debug/event-registrations")
async def debug_event_registrations():
    """
    Debug endpoint to check event registration setup
    """
    try:
        supabase = get_supabase_client()
        
        # Check if event_registrations table exists
        table_check = supabase.table("event_registrations").select("id").limit(1).execute()
        
        # Check users count
        users_count = supabase.table("users").select("id", count="exact").execute()
        
        # Check events count
        events_count = supabase.table("events").select("id", count="exact").execute()
        
        return {
            "status": "ok",
            "event_registrations_table": "exists" if table_check.data is not None else "missing",
            "users_count": users_count.count if users_count.count else 0,
            "events_count": events_count.count if events_count.count else 0,
            "supabase_connected": True
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "supabase_connected": False
        }
