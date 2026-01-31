"""
Scheduled email processing for event reminders and thank-you emails.
This service processes registrations and sends reminder emails for events happening tomorrow,
and thank-you emails for events that completed yesterday.
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import pytz
from db.supabase import get_supabase_client, safe_supabase_operation
from services.event_email_service import send_reminder_email, send_thank_you_email

logger = logging.getLogger(__name__)

# Pacific Time zone
PACIFIC_TZ = pytz.timezone("America/Los_Angeles")


async def process_reminder_emails_for_tomorrow() -> int:
    """
    Process and send reminder emails for events happening tomorrow.
    
    Checks all registrations where:
    - email_status = "confirmation_sent"
    - reminder_sent_at IS NULL (not sent yet)
    - Event date is tomorrow (same calendar day)
    
    Returns:
        Number of reminder emails sent
    """
    try:
        supabase = get_supabase_client()
        
        # Get tomorrow's date in Pacific Time
        pacific_now = datetime.now(PACIFIC_TZ)
        tomorrow = pacific_now + timedelta(days=1)
        tomorrow_start = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_end = tomorrow.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        # Convert to UTC for database query
        tomorrow_start_utc = tomorrow_start.astimezone(pytz.UTC)
        tomorrow_end_utc = tomorrow_end.astimezone(pytz.UTC)
        
        logger.info(f"Processing reminder emails for events on {tomorrow.date()}")
        logger.info(f"Time range (UTC): {tomorrow_start_utc.isoformat()} to {tomorrow_end_utc.isoformat()}")
        
        # Query registrations that need reminders
        def query_registrations():
            return (
                supabase
                .table("event_registrations")
                .select(
                    """
                    id,
                    user_id,
                    event_id,
                    email_status,
                    reminder_sent_at,
                    events!inner(
                        id,
                        title,
                        date_time,
                        location,
                        slug
                    )
                    """
                )
                .eq("email_status", "confirmation_sent")
                .is_("reminder_sent_at", "null")
                .gte("events.date_time", tomorrow_start_utc.isoformat())
                .lte("events.date_time", tomorrow_end_utc.isoformat())
                .execute()
            )
        
        response = await safe_supabase_operation(
            query_registrations,
            "Failed to query registrations for reminders"
        )
        
        registrations = response.data or []
        logger.info(f"Found {len(registrations)} registrations needing reminder emails")
        
        if not registrations:
            return 0
        
        emails_sent = 0
        
        for reg in registrations:
            try:
                event = reg.get("events", {})
                if not event:
                    logger.warning(f"Registration {reg.get('id')} has no event data, skipping")
                    continue
                
                event_id = event.get("id")
                event_title = event.get("title", "Event")
                event_date_time = event.get("date_time")
                event_location = event.get("location", "TBD")
                event_slug = event.get("slug")
                
                user_id = reg.get("user_id")
                
                # Get user email and name
                def get_user_data():
                    # Try users table first
                    user_resp = supabase.table("users").select("email, name").eq("id", user_id).limit(1).execute()
                    if user_resp.data:
                        return user_resp.data[0]
                    # Try admins table
                    admin_resp = supabase.table("admins").select("email, name").eq("id", user_id).limit(1).execute()
                    if admin_resp.data:
                        return admin_resp.data[0]
                    return None
                
                user_data = await safe_supabase_operation(
                    get_user_data,
                    f"Failed to get user data for user {user_id}"
                )
                
                if not user_data:
                    logger.warning(f"User {user_id} not found in users or admins table, skipping")
                    continue
                
                user_email = user_data.get("email")
                user_name = user_data.get("name") or "Valued Member"
                
                if not user_email:
                    logger.warning(f"User {user_id} has no email address, skipping")
                    continue
                
                # Send reminder email
                success = await send_reminder_email(
                    to_email=user_email,
                    user_name=user_name,
                    event_title=event_title,
                    event_date_time=event_date_time,
                    event_location=event_location,
                    event_slug=event_slug,
                )
                
                if success:
                    # Update registration with reminder_sent_at timestamp
                    def update_registration():
                        return (
                            supabase
                            .table("event_registrations")
                            .update({
                                "reminder_sent_at": datetime.utcnow().isoformat(),
                                "email_status": "reminder_sent"
                            })
                            .eq("id", reg.get("id"))
                            .execute()
                        )
                    
                    await safe_supabase_operation(
                        update_registration,
                        f"Failed to update registration {reg.get('id')}"
                    )
                    
                    # Log email in email_logs table (if it exists)
                    try:
                        def log_email():
                            return (
                                supabase
                                .table("email_logs")
                                .insert({
                                    "registration_id": reg.get("id"),
                                    "user_id": user_id,
                                    "event_id": event_id,
                                    "email_type": "reminder",
                                    "recipient_email": user_email,
                                    "sent_at": datetime.utcnow().isoformat(),
                                    "status": "sent"
                                })
                                .execute()
                            )
                        await safe_supabase_operation(log_email, "Failed to log email")
                    except Exception as log_error:
                        # Log table might not exist, that's okay
                        logger.debug(f"Could not log email (table may not exist): {log_error}")
                    
                    emails_sent += 1
                    logger.info(f"Reminder email sent to {user_email} for event: {event_title}")
                else:
                    logger.error(f"Failed to send reminder email to {user_email} for event: {event_title}")
                    
            except Exception as e:
                logger.error(f"Error processing reminder for registration {reg.get('id')}: {e}")
                continue
        
        logger.info(f"Reminder email processing completed. Sent {emails_sent} reminder(s).")
        return emails_sent
        
    except Exception as e:
        logger.error(f"Error in process_reminder_emails_for_tomorrow: {e}")
        raise


async def process_thank_you_emails() -> int:
    """
    Process and send thank-you emails for events that completed yesterday.
    
    Checks all registrations where:
    - email_status IN ("confirmation_sent", "reminder_sent")
    - thank_you_sent_at IS NULL (not sent yet)
    - Event date is yesterday (same calendar day)
    
    Returns:
        Number of thank-you emails sent
    """
    try:
        supabase = get_supabase_client()
        
        # Get yesterday's date in Pacific Time
        pacific_now = datetime.now(PACIFIC_TZ)
        yesterday = pacific_now - timedelta(days=1)
        yesterday_start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_end = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        # Convert to UTC for database query
        yesterday_start_utc = yesterday_start.astimezone(pytz.UTC)
        yesterday_end_utc = yesterday_end.astimezone(pytz.UTC)
        
        logger.info(f"Processing thank-you emails for events on {yesterday.date()}")
        logger.info(f"Time range (UTC): {yesterday_start_utc.isoformat()} to {yesterday_end_utc.isoformat()}")
        
        # Query registrations that need thank-you emails
        def query_registrations():
            return (
                supabase
                .table("event_registrations")
                .select(
                    """
                    id,
                    user_id,
                    event_id,
                    email_status,
                    thank_you_sent_at,
                    events!inner(
                        id,
                        title,
                        date_time,
                        location,
                        slug
                    )
                    """
                )
                .in_("email_status", ["confirmation_sent", "reminder_sent"])
                .is_("thank_you_sent_at", "null")
                .gte("events.date_time", yesterday_start_utc.isoformat())
                .lte("events.date_time", yesterday_end_utc.isoformat())
                .execute()
            )
        
        response = await safe_supabase_operation(
            query_registrations,
            "Failed to query registrations for thank-you emails"
        )
        
        registrations = response.data or []
        logger.info(f"Found {len(registrations)} registrations needing thank-you emails")
        
        if not registrations:
            return 0
        
        emails_sent = 0
        
        for reg in registrations:
            try:
                event = reg.get("events", {})
                if not event:
                    logger.warning(f"Registration {reg.get('id')} has no event data, skipping")
                    continue
                
                event_id = event.get("id")
                event_title = event.get("title", "Event")
                event_date_time = event.get("date_time")
                event_location = event.get("location", "TBD")
                event_slug = event.get("slug")
                
                user_id = reg.get("user_id")
                
                # Get user email and name
                def get_user_data():
                    # Try users table first
                    user_resp = supabase.table("users").select("email, name").eq("id", user_id).limit(1).execute()
                    if user_resp.data:
                        return user_resp.data[0]
                    # Try admins table
                    admin_resp = supabase.table("admins").select("email, name").eq("id", user_id).limit(1).execute()
                    if admin_resp.data:
                        return admin_resp.data[0]
                    return None
                
                user_data = await safe_supabase_operation(
                    get_user_data,
                    f"Failed to get user data for user {user_id}"
                )
                
                if not user_data:
                    logger.warning(f"User {user_id} not found in users or admins table, skipping")
                    continue
                
                user_email = user_data.get("email")
                user_name = user_data.get("name") or "Valued Member"
                
                if not user_email:
                    logger.warning(f"User {user_id} has no email address, skipping")
                    continue
                
                # Send thank-you email
                success = await send_thank_you_email(
                    to_email=user_email,
                    user_name=user_name,
                    event_title=event_title,
                    event_date_time=event_date_time,
                    event_location=event_location,
                    event_slug=event_slug,
                )
                
                if success:
                    # Update registration with thank_you_sent_at timestamp
                    def update_registration():
                        return (
                            supabase
                            .table("event_registrations")
                            .update({
                                "thank_you_sent_at": datetime.utcnow().isoformat(),
                                "email_status": "thank_you_sent"
                            })
                            .eq("id", reg.get("id"))
                            .execute()
                        )
                    
                    await safe_supabase_operation(
                        update_registration,
                        f"Failed to update registration {reg.get('id')}"
                    )
                    
                    # Log email in email_logs table (if it exists)
                    try:
                        def log_email():
                            return (
                                supabase
                                .table("email_logs")
                                .insert({
                                    "registration_id": reg.get("id"),
                                    "user_id": user_id,
                                    "event_id": event_id,
                                    "email_type": "thank_you",
                                    "recipient_email": user_email,
                                    "sent_at": datetime.utcnow().isoformat(),
                                    "status": "sent"
                                })
                                .execute()
                            )
                        await safe_supabase_operation(log_email, "Failed to log email")
                    except Exception as log_error:
                        # Log table might not exist, that's okay
                        logger.debug(f"Could not log email (table may not exist): {log_error}")
                    
                    emails_sent += 1
                    logger.info(f"Thank-you email sent to {user_email} for event: {event_title}")
                else:
                    logger.error(f"Failed to send thank-you email to {user_email} for event: {event_title}")
                    
            except Exception as e:
                logger.error(f"Error processing thank-you for registration {reg.get('id')}: {e}")
                continue
        
        logger.info(f"Thank-you email processing completed. Sent {emails_sent} thank-you email(s).")
        return emails_sent
        
    except Exception as e:
        logger.error(f"Error in process_thank_you_emails: {e}")
        raise

