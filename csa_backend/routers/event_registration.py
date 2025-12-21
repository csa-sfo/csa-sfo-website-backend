import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from supabase import create_client, Client
import os
from typing import Optional
from datetime import datetime, timedelta
import pytz
from services.auth_services import verify_admin_token
from services.event_email_service import send_event_email

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
        
        # Validate user exists in either users or admins table and get full details
        user_response = supabase.table("users").select("id, email, name").eq("id", registration.user_id).limit(1).execute()
        admin_response = supabase.table("admins").select("id, email, name").eq("id", registration.user_id).limit(1).execute()
        
        if not user_response.data and not admin_response.data:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Get user data
        user_data = user_response.data[0] if user_response.data else admin_response.data[0]
        user_email = user_data.get("email")
        user_name = user_data.get("name", "Valued Member")
        
        # Validate event exists and get full details
        event_response = supabase.table("events").select("id, title, capacity, attendees, date_time, location, slug").eq("id", registration.event_id).limit(1).execute()
        if not event_response.data:
            raise HTTPException(status_code=404, detail="Event not found")
        
        event_data = event_response.data[0]
        
        # Check if user is already registered - return existing registration instead of error
        existing_registration = supabase.table("event_registrations").select("id, email_status").eq(
            "user_id", registration.user_id
        ).eq("event_id", registration.event_id).limit(1).execute()
        
        if existing_registration.data:
            existing_reg = existing_registration.data[0]
            logging.info(f"User already registered (create_event_registration), returning existing {existing_reg['id']}")
            return EventRegistrationResponse(
                id=existing_reg["id"],
                user_id=registration.user_id,
                event_id=registration.event_id,
                message="Already registered for this event"
            )
        
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
        
        # Send confirmation email immediately (fire and forget - don't block registration)
        try:
            # Format event date and time
            timezone = pytz.timezone("America/Los_Angeles")
            event_start = datetime.fromisoformat(event_data["date_time"].replace('Z', '+00:00'))
            if event_start.tzinfo is None:
                event_start = pytz.UTC.localize(event_start)
            event_start_local = event_start.astimezone(timezone)
            
            event_date = event_start_local.strftime("%B %d, %Y")
            event_time = event_start_local.strftime("%I:%M %p %Z")
            
            # Calculate hours until event
            now = datetime.now(timezone)
            hours_until_event = (event_start_local - now).total_seconds() / 3600
            
            # Send confirmation email
            email_result = await send_event_email(
                email_type="confirmation",
                to_email=user_email,
                user_name=user_name,
                event_title=event_data["title"],
                event_date=event_date,
                event_time=event_time,
                event_location=event_data.get("location", "TBA"),
                event_slug=event_data.get("slug")
            )
            
            if email_result["success"]:
                # Only send confirmation - reminder will be sent by scheduler 24h before event
                supabase.table("event_registrations").update({
                    "email_status": "confirmation_sent",
                    "confirmation_sent_at": datetime.utcnow().isoformat()
                }).eq("id", registration_id).execute()
                logging.info(f"Confirmation email sent for registration {registration_id}")
                
                # Schedule reminder and thank-you emails
                try:
                    from apscheduler.triggers.date import DateTrigger
                    from services.event_email_scheduler import send_reminder_for_registration, send_thank_you_for_registration, scheduler
                    import asyncio
                    
                    # Schedule reminder email 24 hours before event
                    reminder_time = event_start_local - timedelta(hours=24)
                    if reminder_time > now and scheduler is not None:
                        scheduler.add_job(
                            lambda: asyncio.run(send_reminder_for_registration(registration_id)),
                            trigger=DateTrigger(run_date=reminder_time),
                            id=f'reminder_{registration_id}',
                            replace_existing=True
                        )
                        logging.info(f"Scheduled reminder for registration {registration_id} at {reminder_time}")
                    elif reminder_time <= now:
                        logging.info(f"Event is less than 24h away, skipping reminder scheduling for {registration_id}")
                    
                    # Schedule thank-you email 24 hours after event start
                    thank_you_time = event_start_local + timedelta(hours=24)
                    if thank_you_time > now and scheduler is not None:
                        scheduler.add_job(
                            lambda: asyncio.run(send_thank_you_for_registration(registration_id)),
                            trigger=DateTrigger(run_date=thank_you_time),
                            id=f'thank_you_{registration_id}',
                            replace_existing=True
                        )
                        logging.info(f"Scheduled thank-you for registration {registration_id} at {thank_you_time}")
                    elif thank_you_time <= now:
                        logging.info(f"Event already passed 24h, skipping thank-you scheduling for {registration_id}")
                    
                    if scheduler is None:
                        logging.warning(f"Scheduler not available, emails will be handled by polling")
                except Exception as schedule_error:
                    logging.warning(f"Failed to schedule emails for {registration_id}: {schedule_error}")
                    # Don't fail registration if scheduling fails - polling will handle it
            else:
                # Email failed but registration succeeded
                supabase.table("event_registrations").update({
                    "email_status": "failed",
                    "email_error": email_result.get("error", "Unknown error")
                }).eq("id", registration_id).execute()
                logging.error(f"Failed to send confirmation email for {registration_id}: {email_result.get('error')}")
        except Exception as email_error:
            # Log error but don't fail registration
            logging.error(f"Error sending confirmation email for {registration_id}: {email_error}")
            supabase.table("event_registrations").update({
                "email_error": str(email_error)
            }).eq("id", registration_id).execute()
        
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
        
        # Get user data
        user_response = supabase.table("users").select("id, email, name").eq("id", registration.user_id).limit(1).execute()
        admin_response = supabase.table("admins").select("id, email, name").eq("id", registration.user_id).limit(1).execute()
        
        user_data = user_response.data[0] if user_response.data else (admin_response.data[0] if admin_response.data else None)
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_email = user_data.get("email")
        user_name = user_data.get("name", "Valued Member")
        
        # Get event details with full info
        event_response = supabase.table("events").select("id, title, attendees, capacity, date_time, location, slug").eq("id", registration.event_id).limit(1).execute()
        if not event_response.data:
            raise HTTPException(status_code=404, detail="Event not found")
        
        event_data = event_response.data[0]
        
        # Check if user is already registered - return existing instead of error
        existing_registration = supabase.table("event_registrations").select("id, email_status").eq(
            "user_id", registration.user_id
        ).eq("event_id", registration.event_id).limit(1).execute()
        
        if existing_registration.data:
            existing_reg = existing_registration.data[0]
            logging.info(f"User already registered (simple_registration), returning existing {existing_reg['id']}")
            return EventRegistrationResponse(
                id=existing_reg["id"],
                user_id=registration.user_id,
                event_id=registration.event_id,
                message="Already registered for this event"
            )
        
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
        
        # Send confirmation email immediately
        try:
            timezone = pytz.timezone("America/Los_Angeles")
            event_start = datetime.fromisoformat(event_data["date_time"].replace('Z', '+00:00'))
            if event_start.tzinfo is None:
                event_start = pytz.UTC.localize(event_start)
            event_start_local = event_start.astimezone(timezone)
            
            event_date = event_start_local.strftime("%B %d, %Y")
            event_time = event_start_local.strftime("%I:%M %p %Z")
            
            now = datetime.now(timezone)
            hours_until_event = (event_start_local - now).total_seconds() / 3600
            
            email_result = await send_event_email(
                email_type="confirmation",
                to_email=user_email,
                user_name=user_name,
                event_title=event_data["title"],
                event_date=event_date,
                event_time=event_time,
                event_location=event_data.get("location", "TBA"),
                event_slug=event_data.get("slug")
            )
            
            if email_result["success"]:
                # Only send confirmation - reminder will be sent by scheduler 24h before event
                supabase.table("event_registrations").update({
                    "email_status": "confirmation_sent",
                    "confirmation_sent_at": datetime.utcnow().isoformat()
                }).eq("id", registration_id).execute()
                logging.info(f"Confirmation email sent for registration {registration_id}")
                
                # Schedule reminder and thank-you emails
                try:
                    from apscheduler.triggers.date import DateTrigger
                    from services.event_email_scheduler import send_reminder_for_registration, send_thank_you_for_registration, scheduler
                    import asyncio
                    
                    # Schedule reminder email 24 hours before event
                    reminder_time = event_start_local - timedelta(hours=24)
                    if reminder_time > now and scheduler is not None:
                        scheduler.add_job(
                            lambda: asyncio.run(send_reminder_for_registration(registration_id)),
                            trigger=DateTrigger(run_date=reminder_time),
                            id=f'reminder_{registration_id}',
                            replace_existing=True
                        )
                        logging.info(f"Scheduled reminder for registration {registration_id} at {reminder_time}")
                    elif reminder_time <= now:
                        logging.info(f"Event is less than 24h away, skipping reminder scheduling for {registration_id}")
                    
                    # Schedule thank-you email 24 hours after event start
                    thank_you_time = event_start_local + timedelta(hours=24)
                    if thank_you_time > now and scheduler is not None:
                        scheduler.add_job(
                            lambda: asyncio.run(send_thank_you_for_registration(registration_id)),
                            trigger=DateTrigger(run_date=thank_you_time),
                            id=f'thank_you_{registration_id}',
                            replace_existing=True
                        )
                        logging.info(f"Scheduled thank-you for registration {registration_id} at {thank_you_time}")
                    elif thank_you_time <= now:
                        logging.info(f"Event already passed 24h, skipping thank-you scheduling for {registration_id}")
                    
                    if scheduler is None:
                        logging.warning(f"Scheduler not available, emails will be handled by polling")
                except Exception as schedule_error:
                    logging.warning(f"Failed to schedule emails for {registration_id}: {schedule_error}")
                    # Don't fail registration if scheduling fails - polling will handle it
            else:
                supabase.table("event_registrations").update({
                    "email_status": "failed",
                    "email_error": email_result.get("error", "Unknown error")
                }).eq("id", registration_id).execute()
        except Exception as email_error:
            logging.error(f"Error sending email for {registration_id}: {email_error}")
            supabase.table("event_registrations").update({
                "email_error": str(email_error)
            }).eq("id", registration_id).execute()
        
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

@event_registration_router.delete("/event-registrations/delete/{event_id}/{user_id}")
async def delete_event_registration(event_id: str, user_id: str, token_data: dict = Depends(verify_admin_token)):
    """
    Delete a user's registration for a specific event (Admin only).
    Also updates the event's attendee count.
    """
    admin_email = token_data.get("email", "Unknown")
    logging.info(f"Admin {admin_email} is deleting registration for user {user_id} from event {event_id}")
    
    try:
        supabase = get_supabase_client()
        
        # Check if registration exists
        reg_check = supabase.table("event_registrations").select("id").eq("user_id", user_id).eq("event_id", event_id).execute()
        
        if not reg_check.data or len(reg_check.data) == 0:
            raise HTTPException(status_code=404, detail="Registration not found")
        
        # Get current event attendees count
        event_resp = supabase.table("events").select("id, attendees").eq("id", event_id).limit(1).execute()
        if not event_resp.data:
            raise HTTPException(status_code=404, detail="Event not found")
        
        current_attendees = event_resp.data[0].get("attendees", 0)
        
        # Delete the registration
        delete_resp = supabase.table("event_registrations").delete().eq("user_id", user_id).eq("event_id", event_id).execute()
        
        if not delete_resp.data:
            raise HTTPException(status_code=500, detail="Failed to delete registration")
        
        # Update event attendees count
        new_attendees = max(0, current_attendees - 1)
        supabase.table("events").update({"attendees": new_attendees}).eq("id", event_id).execute()
        
        logging.info(f"Admin {admin_email} successfully deleted registration and updated attendees: {current_attendees} -> {new_attendees}")
        
        return {
            "message": "Registration deleted successfully",
            "event_id": event_id,
            "user_id": user_id,
            "previous_attendees": current_attendees,
            "updated_attendees": new_attendees
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error deleting event registration: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting registration: {str(e)}")

@event_registration_router.post("/resend-email/{registration_id}")
async def resend_registration_email(registration_id: str):
    """
    Resend confirmation email for an existing registration.
    Useful if email wasn't sent initially.
    """
    try:
        supabase = get_supabase_client()
        
        # Get registration with user and event details
        reg_response = supabase.table("event_registrations").select(
            """
            id,
            user_id,
            event_id,
            email_status,
            events!inner(id, title, date_time, location, slug)
            """
        ).eq("id", registration_id).limit(1).execute()
        
        if not reg_response.data:
            raise HTTPException(status_code=404, detail="Registration not found")
        
        reg = reg_response.data[0]
        
        # Get user data
        user_response = supabase.table("users").select("id, email, name").eq("id", reg["user_id"]).limit(1).execute()
        admin_response = supabase.table("admins").select("id, email, name").eq("id", reg["user_id"]).limit(1).execute()
        
        user_data = user_response.data[0] if user_response.data else (admin_response.data[0] if admin_response.data else None)
        if not user_data or not user_data.get("email"):
            raise HTTPException(status_code=404, detail="User email not found")
        
        event_data = reg.get("events")
        if not event_data:
            raise HTTPException(status_code=404, detail="Event not found")
        
        # Format event date and time
        timezone = pytz.timezone("America/Los_Angeles")
        event_start = datetime.fromisoformat(event_data["date_time"].replace('Z', '+00:00'))
        if event_start.tzinfo is None:
            event_start = pytz.UTC.localize(event_start)
        event_start_local = event_start.astimezone(timezone)
        
        event_date = event_start_local.strftime("%B %d, %Y")
        event_time = event_start_local.strftime("%I:%M %p %Z")
        
        # Send confirmation email
        email_result = await send_event_email(
            email_type="confirmation",
            to_email=user_data["email"],
            user_name=user_data.get("name", "Valued Member"),
            event_title=event_data["title"],
            event_date=event_date,
            event_time=event_time,
            event_location=event_data.get("location", "TBA"),
            event_slug=event_data.get("slug")
        )
        
        if email_result["success"]:
            # Update registration status
            supabase.table("event_registrations").update({
                "email_status": "confirmation_sent",
                "confirmation_sent_at": datetime.utcnow().isoformat(),
                "email_error": None
            }).eq("id", registration_id).execute()
            
            return {
                "success": True,
                "message": "Confirmation email sent successfully",
                "message_id": email_result["message_id"]
            }
        else:
            # Update with error
            supabase.table("event_registrations").update({
                "email_status": "failed",
                "email_error": email_result.get("error", "Unknown error")
            }).eq("id", registration_id).execute()
            
            raise HTTPException(
                status_code=500,
                detail=f"Failed to send email: {email_result.get('error')}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error resending email: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to resend email: {str(e)}")

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
