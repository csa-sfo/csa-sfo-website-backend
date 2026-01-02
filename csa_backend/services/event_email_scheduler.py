"""
Email Automation for Event Notifications
Handles sending reminder emails for events tomorrow and thank-you emails for events yesterday
Works with existing event_registrations table schema
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any
import pytz

from db.supabase import get_supabase_client, safe_supabase_operation
from services.event_email_service import send_event_email

logger = logging.getLogger(__name__)

TIMEZONE = pytz.timezone("America/Los_Angeles")


def format_datetime(dt_str: str) -> tuple[str, str]:
    """Format ISO datetime string to readable date and time"""
    try:
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt)
        dt_local = dt.astimezone(TIMEZONE)
        
        date_str = dt_local.strftime("%B %d, %Y")
        time_str = dt_local.strftime("%I:%M %p %Z")
        
        return date_str, time_str
    except Exception as e:
        logger.warning(f"Error formatting datetime {dt_str}: {e}")
        return dt_str, "TBA"


async def send_confirmation_and_reminder_together(
    registration_id: str,
    user_email: str,
    user_name: str,
    event_title: str,
    event_date: str,
    event_time: str,
    event_location: str,
    event_slug: str = None
) -> dict:
    """Send both confirmation and reminder emails together for late registrations
    
    This is used when:
    - User registers less than 24 hours before the event
    - Event is happening tomorrow (next day) when user registers
    
    Returns dict with success status and any errors
    """
    try:
        supabase = get_supabase_client()
        now = datetime.utcnow()
        
        # Send confirmation email
        confirmation_result = await send_event_email(
            email_type="confirmation",
            to_email=user_email,
            user_name=user_name,
            event_title=event_title,
            event_date=event_date,
            event_time=event_time,
            event_location=event_location,
            event_slug=event_slug
        )
        
        if not confirmation_result["success"]:
            return {
                "success": False,
                "error": f"Confirmation email failed: {confirmation_result.get('error')}",
                "confirmation_sent": False,
                "reminder_sent": False
            }
        
        # Log confirmation email
        log_query = lambda: (
            supabase
            .table("email_logs")
            .insert({
                "registration_id": registration_id,
                "email_type": "confirmation",
                "recipient_email": user_email,
                "status": "sent",
                "aws_message_id": confirmation_result["message_id"]
            })
            .execute()
        )
        await safe_supabase_operation(log_query, "Failed to log confirmation")
        
        # Send reminder email immediately after confirmation
        reminder_result = await send_event_email(
            email_type="reminder",
            to_email=user_email,
            user_name=user_name,
            event_title=event_title,
            event_date=event_date,
            event_time=event_time,
            event_location=event_location,
            event_slug=event_slug
        )
        
        if not reminder_result["success"]:
            # Confirmation sent but reminder failed - update status accordingly
            update_query = lambda: (
                supabase
                .table("event_registrations")
                .update({
                    "email_status": "confirmation_sent",
                    "confirmation_sent_at": now.isoformat(),
                    "email_error": f"Reminder failed: {reminder_result.get('error')}"
                })
                .eq("id", registration_id)
                .execute()
            )
            await safe_supabase_operation(update_query, "Failed to update status")
            
            return {
                "success": False,
                "error": f"Reminder email failed: {reminder_result.get('error')}",
                "confirmation_sent": True,
                "reminder_sent": False
            }
        
        # Both emails sent successfully - update registration status
        update_query = lambda: (
            supabase
            .table("event_registrations")
            .update({
                "email_status": "reminder_sent",
                "confirmation_sent_at": now.isoformat(),
                "reminder_sent_at": now.isoformat(),
                "email_error": None
            })
            .eq("id", registration_id)
            .execute()
        )
        await safe_supabase_operation(update_query, "Failed to update registration")
        
        # Log reminder email
        log_query = lambda: (
            supabase
            .table("email_logs")
            .insert({
                "registration_id": registration_id,
                "email_type": "reminder",
                "recipient_email": user_email,
                "status": "sent",
                "aws_message_id": reminder_result["message_id"]
            })
            .execute()
        )
        await safe_supabase_operation(log_query, "Failed to log reminder")
        
        logger.info(f"Sent both confirmation and reminder emails for registration {registration_id}")
        
        return {
            "success": True,
            "confirmation_sent": True,
            "reminder_sent": True,
            "confirmation_message_id": confirmation_result["message_id"],
            "reminder_message_id": reminder_result["message_id"]
        }
        
    except Exception as e:
        logger.error(f"Error sending confirmation and reminder together for {registration_id}: {e}")
        return {
            "success": False,
            "error": str(e),
            "confirmation_sent": False,
            "reminder_sent": False
        }


async def process_pending_confirmations():
    """Send confirmation emails for registrations with email_status = 'pending'
    
    Note: Reminders are handled separately by process_reminder_emails() 24h before event.
    This function only sends confirmations.
    """
    try:
        supabase = get_supabase_client()
        now = datetime.now(TIMEZONE)
        
        # Get registrations pending confirmation
        query = lambda: (
            supabase
            .table("event_registrations")
            .select("""
                id,
                user_id,
                event_id,
                events!inner(
                    id,
                    title,
                    date_time,
                    location,
                    slug
                )
            """)
            .eq("email_status", "pending")
            .limit(50)
            .execute()
        )
        
        response = await safe_supabase_operation(query, "Failed to fetch pending confirmations")
        
        if not response.data:
            return 0
        
        sent_count = 0
        
        for reg in response.data:
            try:
                # Fetch user data (try users table first, then admins)
                user_query = lambda: (
                    supabase
                    .table("users")
                    .select("id, email, name")
                    .eq("id", reg["user_id"])
                    .limit(1)
                    .execute()
                )
                user_resp = await safe_supabase_operation(user_query, "Failed to fetch user")
                user_data = user_resp.data[0] if user_resp.data else None
                
                # If not found in users, try admins table
                if not user_data:
                    admin_query = lambda: (
                        supabase
                        .table("admins")
                        .select("id, email, name")
                        .eq("id", reg["user_id"])
                        .limit(1)
                        .execute()
                    )
                    admin_resp = await safe_supabase_operation(admin_query, "Failed to fetch admin")
                    user_data = admin_resp.data[0] if admin_resp.data else None
                
                if not user_data or not user_data.get("email"):
                    logger.warning(f"No email found for registration {reg['id']}")
                    # Mark as failed
                    update_query = lambda: (
                        supabase
                        .table("event_registrations")
                        .update({
                            "email_status": "failed",
                            "email_error": "User email not found"
                        })
                        .eq("id", reg["id"])
                        .execute()
                    )
                    await safe_supabase_operation(update_query, "Failed to update status")
                    continue
                
                event_data = reg.get("events")
                if not event_data:
                    logger.warning(f"No event data for registration {reg['id']}")
                    continue
                
                # Parse event start time
                event_start = datetime.fromisoformat(
                    event_data["date_time"].replace('Z', '+00:00')
                )
                if event_start.tzinfo is None:
                    event_start = pytz.UTC.localize(event_start)
                event_start_local = event_start.astimezone(TIMEZONE)
                
                # Calculate hours until event
                hours_until_event = (event_start_local - now).total_seconds() / 3600
                
                # Skip if event already passed
                if hours_until_event < 0:
                    logger.info(f"Event already passed for registration {reg['id']}, skipping")
                    update_query = lambda: (
                        supabase
                        .table("event_registrations")
                        .update({
                            "email_status": "cancelled",
                            "email_error": "Event already passed"
                        })
                        .eq("id", reg["id"])
                        .execute()
                    )
                    await safe_supabase_operation(update_query, "Failed to update status")
                    continue
                
                event_date, event_time = format_datetime(event_data["date_time"])
                
                # Check if event is within 24 hours or happening tomorrow
                tomorrow = now + timedelta(days=1)
                is_within_24h = hours_until_event < 24
                is_tomorrow = event_start_local.date() == tomorrow.date() and event_start_local > now
                
                # If within 24 hours or happening tomorrow, send both confirmation and reminder
                if is_within_24h or is_tomorrow:
                    logger.info(f"Event within 24h or tomorrow for registration {reg['id']}, sending both confirmation and reminder")
                    result = await send_confirmation_and_reminder_together(
                        registration_id=reg["id"],
                        user_email=user_data["email"],
                        user_name=user_data.get("name", "Valued Member"),
                        event_title=event_data["title"],
                        event_date=event_date,
                        event_time=event_time,
                        event_location=event_data.get("location", "TBA"),
                        event_slug=event_data.get("slug")
                    )
                    
                    if result["success"]:
                        sent_count += 1
                        logger.info(f"Confirmation and reminder sent together for registration {reg['id']} ({hours_until_event:.1f}h before event)")
                    else:
                        # Update with error
                        update_query = lambda: (
                            supabase
                            .table("event_registrations")
                            .update({
                                "email_status": "failed",
                                "email_error": result.get("error", "Unknown error")
                            })
                            .eq("id", reg["id"])
                            .execute()
                        )
                        await safe_supabase_operation(update_query, "Failed to update error")
                        logger.error(f"Failed to send emails for {reg['id']}: {result.get('error')}")
                else:
                    # Send only confirmation email (reminder will be sent by daily job)
                    result = await send_event_email(
                        email_type="confirmation",
                        to_email=user_data["email"],
                        user_name=user_data.get("name", "Valued Member"),
                        event_title=event_data["title"],
                        event_date=event_date,
                        event_time=event_time,
                        event_location=event_data.get("location", "TBA"),
                        event_slug=event_data.get("slug")
                    )
                    
                    if result["success"]:
                        # Confirmation sent - reminders will be handled by daily check for events tomorrow
                        update_query = lambda: (
                            supabase
                            .table("event_registrations")
                            .update({
                                "email_status": "confirmation_sent",
                                "confirmation_sent_at": datetime.utcnow().isoformat(),
                                "email_error": None
                            })
                            .eq("id", reg["id"])
                            .execute()
                        )
                        await safe_supabase_operation(update_query, "Failed to update registration")
                        
                        # Log confirmation email
                        log_query = lambda: (
                            supabase
                            .table("email_logs")
                            .insert({
                                "registration_id": reg["id"],
                                "email_type": "confirmation",
                                "recipient_email": user_data["email"],
                                "status": "sent",
                                "aws_message_id": result["message_id"]
                            })
                            .execute()
                        )
                        await safe_supabase_operation(log_query, "Failed to log email")
                        
                        sent_count += 1
                        logger.info(f"Confirmation sent for registration {reg['id']} ({hours_until_event:.1f}h before event)")
                    else:
                        # Update with error - set status to 'failed' per your schema
                        update_query = lambda: (
                            supabase
                            .table("event_registrations")
                            .update({
                                "email_status": "failed",
                                "email_error": result["error"]
                            })
                            .eq("id", reg["id"])
                            .execute()
                        )
                        await safe_supabase_operation(update_query, "Failed to update error")
                        
                        logger.error(f"Failed to send confirmation for {reg['id']}: {result['error']}")
                    
            except Exception as e:
                logger.error(f"Error processing registration {reg.get('id', 'unknown')}: {e}")
                # Mark as failed
                try:
                    update_query = lambda: (
                        supabase
                        .table("event_registrations")
                        .update({
                            "email_status": "failed",
                            "email_error": str(e)
                        })
                        .eq("id", reg["id"])
                        .execute()
                    )
                    await safe_supabase_operation(update_query, "Failed to update error")
                except:
                    pass
                continue
        
        logger.info(f"Processed {sent_count} confirmation emails")
        return sent_count
        
    except Exception as e:
        logger.error(f"Error in process_pending_confirmations: {e}")
        return 0


async def process_reminder_emails_for_tomorrow():
    """Send reminder emails for events happening tomorrow (within next 24 hours)
    
    IMPORTANT: Each reminder email is sent ONLY ONCE per registration.
    The query filters for reminder_sent_at IS NULL, and after sending,
    reminder_sent_at is set to a timestamp, preventing duplicate sends.
    
    Only processes registrations that:
    - Have confirmation_sent status
    - Event is happening tomorrow (within next 24 hours)
    - Reminder hasn't been sent yet (reminder_sent_at IS NULL)
    """
    try:
        supabase = get_supabase_client()
        now = datetime.now(TIMEZONE)
        tomorrow = now + timedelta(days=1)
        
        # Calculate window: events starting between now and 24 hours from now
        now_utc = now.astimezone(pytz.UTC)
        tomorrow_utc = tomorrow.astimezone(pytz.UTC)
        
        logger.info(f"Checking for reminder emails: events happening tomorrow (between {now_utc.isoformat()} and {tomorrow_utc.isoformat()})")
        
        # Fetch all candidates
        query = lambda: (
            supabase
            .table("event_registrations")
            .select("""
                id,
                user_id,
                event_id,
                events!inner(
                    id,
                    title,
                    date_time,
                    location,
                    slug
                )
            """)
            .eq("email_status", "confirmation_sent")
            .is_("reminder_sent_at", "null")
            .limit(500)
            .execute()
        )
        
        response = await safe_supabase_operation(query, "Failed to fetch reminder candidates")
        
        if not response.data:
            return 0
        
        logger.debug(f"Found {len(response.data)} reminder candidates to check")
        
        sent_count = 0
        
        for reg in response.data:
            try:
                # Fetch user data
                user_query = lambda: (
                    supabase
                    .table("users")
                    .select("id, email, name")
                    .eq("id", reg["user_id"])
                    .limit(1)
                    .execute()
                )
                user_resp = await safe_supabase_operation(user_query, "Failed to fetch user")
                user_data = user_resp.data[0] if user_resp.data else None
                
                if not user_data:
                    admin_query = lambda: (
                        supabase
                        .table("admins")
                        .select("id, email, name")
                        .eq("id", reg["user_id"])
                        .limit(1)
                        .execute()
                    )
                    admin_resp = await safe_supabase_operation(admin_query, "Failed to fetch admin")
                    user_data = admin_resp.data[0] if admin_resp.data else None
                
                if not user_data or not user_data.get("email"):
                    continue
                
                event_data = reg.get("events")
                if not event_data:
                    continue
                
                # Check if event is happening tomorrow (within next 24 hours)
                event_start = datetime.fromisoformat(
                    event_data["date_time"].replace('Z', '+00:00')
                )
                if event_start.tzinfo is None:
                    event_start = pytz.UTC.localize(event_start)
                event_start_local = event_start.astimezone(TIMEZONE)
                
                # Event must be in the future and within next 24 hours
                if event_start_local <= now or event_start_local > tomorrow:
                    continue
                
                logger.info(
                    f"Processing reminder for {reg['id']}: event '{event_data['title']}' is happening tomorrow at {event_start_local}"
                )
                
                event_date, event_time = format_datetime(event_data["date_time"])
                
                result = await send_event_email(
                    email_type="reminder",
                    to_email=user_data["email"],
                    user_name=user_data.get("name", "Valued Member"),
                    event_title=event_data["title"],
                    event_date=event_date,
                    event_time=event_time,
                    event_location=event_data.get("location", "TBA"),
                    event_slug=event_data.get("slug")
                )
                
                if result["success"]:
                    update_query = lambda: (
                        supabase
                        .table("event_registrations")
                        .update({
                            "email_status": "reminder_sent",
                            "reminder_sent_at": datetime.utcnow().isoformat()
                        })
                        .eq("id", reg["id"])
                        .execute()
                    )
                    await safe_supabase_operation(update_query, "Failed to update reminder")
                    
                    log_query = lambda: (
                        supabase
                        .table("email_logs")
                        .insert({
                            "registration_id": reg["id"],
                            "email_type": "reminder",
                            "recipient_email": user_data["email"],
                            "status": "sent",
                            "aws_message_id": result["message_id"]
                        })
                        .execute()
                    )
                    await safe_supabase_operation(log_query, "Failed to log reminder")
                    
                    sent_count += 1
                    logger.info(f"Reminder sent for registration {reg['id']} (event tomorrow)")
                else:
                    logger.error(f"Failed to send reminder for {reg['id']}: {result['error']}")
                    # Update error but keep status as confirmation_sent
                    update_query = lambda: (
                        supabase
                        .table("event_registrations")
                        .update({
                            "email_error": f"Reminder failed: {result['error']}"
                        })
                        .eq("id", reg["id"])
                        .execute()
                    )
                    await safe_supabase_operation(update_query, "Failed to update error")
                    
            except Exception as e:
                logger.error(f"Error processing reminder for {reg.get('id', 'unknown')}: {e}")
                continue
        
        if sent_count > 0:
            logger.info(f"Sent {sent_count} reminder emails for events tomorrow")
        return sent_count
        
    except Exception as e:
        logger.error(f"Error in process_reminder_emails_for_tomorrow: {e}")
        return 0


async def process_thank_you_emails_for_yesterday():
    """Send thank-you emails for events that completed yesterday (24 hours ago)
    
    IMPORTANT: Each thank-you email is sent ONLY ONCE per registration.
    The query filters for thank_you_sent_at IS NULL, and after sending,
    thank_you_sent_at is set to a timestamp, preventing duplicate sends.
    
    Only processes registrations that:
    - Have confirmation_sent or reminder_sent status
    - Event completed yesterday (started approximately 24 hours ago)
    - Thank-you hasn't been sent yet (thank_you_sent_at IS NULL)
    """
    try:
        supabase = get_supabase_client()
        now = datetime.now(TIMEZONE)
        
        # Calculate window: events that started yesterday (approximately 24 hours ago)
        # Use a window of 20-28 hours ago to account for daily check timing variations
        window_start = now - timedelta(hours=28)  # 28 hours ago
        window_end = now - timedelta(hours=20)    # 20 hours ago
        
        logger.info(f"Checking for thank-you emails: events that completed yesterday (started between {window_start.isoformat()} and {window_end.isoformat()})")
        
        query = lambda: (
            supabase
            .table("event_registrations")
            .select("""
                id,
                user_id,
                event_id,
                events!inner(
                    id,
                    title,
                    date_time,
                    location,
                    slug
                )
            """)
            .in_("email_status", ["confirmation_sent", "reminder_sent"])
            .is_("thank_you_sent_at", "null")
            .limit(500)
            .execute()
        )
        
        response = await safe_supabase_operation(query, "Failed to fetch thank-you candidates")
        
        if not response.data:
            return 0
        
        logger.debug(f"Found {len(response.data)} thank-you candidates to check")
        
        sent_count = 0
        
        for reg in response.data:
            try:
                event_data = reg.get("events")
                if not event_data:
                    continue
                
                # Parse event start time
                event_start = datetime.fromisoformat(
                    event_data["date_time"].replace('Z', '+00:00')
                )
                if event_start.tzinfo is None:
                    event_start = pytz.UTC.localize(event_start)
                event_start_local = event_start.astimezone(TIMEZONE)
                
                # Check if event started yesterday (approximately 24 hours ago, within 20-28 hour window)
                if event_start_local < window_start or event_start_local > window_end:
                    continue
                
                logger.info(
                    f"Processing thank-you for {reg['id']}: event '{event_data['title']}' completed yesterday (started at {event_start_local})"
                )
                
                # Fetch user data
                user_query = lambda: (
                    supabase
                    .table("users")
                    .select("id, email, name")
                    .eq("id", reg["user_id"])
                    .limit(1)
                    .execute()
                )
                user_resp = await safe_supabase_operation(user_query, "Failed to fetch user")
                user_data = user_resp.data[0] if user_resp.data else None
                
                if not user_data:
                    admin_query = lambda: (
                        supabase
                        .table("admins")
                        .select("id, email, name")
                        .eq("id", reg["user_id"])
                        .limit(1)
                        .execute()
                    )
                    admin_resp = await safe_supabase_operation(admin_query, "Failed to fetch admin")
                    user_data = admin_resp.data[0] if admin_resp.data else None
                
                if not user_data or not user_data.get("email"):
                    continue
                
                event_date, event_time = format_datetime(event_data["date_time"])
                
                result = await send_event_email(
                    email_type="thank_you",
                    to_email=user_data["email"],
                    user_name=user_data.get("name", "Valued Member"),
                    event_title=event_data["title"],
                    event_date=event_date,
                    event_time=event_time,
                    event_location=event_data.get("location", "TBA"),
                    event_slug=event_data.get("slug")
                )
                
                if result["success"]:
                    update_query = lambda: (
                        supabase
                        .table("event_registrations")
                        .update({
                            "email_status": "thank_you_sent",
                            "thank_you_sent_at": datetime.utcnow().isoformat()
                        })
                        .eq("id", reg["id"])
                        .execute()
                    )
                    await safe_supabase_operation(update_query, "Failed to update thank-you")
                    
                    log_query = lambda: (
                        supabase
                        .table("email_logs")
                        .insert({
                            "registration_id": reg["id"],
                            "email_type": "thank_you",
                            "recipient_email": user_data["email"],
                            "status": "sent",
                            "aws_message_id": result["message_id"]
                        })
                        .execute()
                    )
                    await safe_supabase_operation(log_query, "Failed to log thank-you")
                    
                    sent_count += 1
                    logger.info(f"Thank-you sent for registration {reg['id']} (event completed yesterday)")
                else:
                    logger.error(f"Failed to send thank-you for {reg['id']}: {result['error']}")
                    # Update error but keep status
                    update_query = lambda: (
                        supabase
                        .table("event_registrations")
                        .update({
                            "email_error": f"Thank-you failed: {result['error']}"
                        })
                        .eq("id", reg["id"])
                        .execute()
                    )
                    await safe_supabase_operation(update_query, "Failed to update error")
                    
            except Exception as e:
                logger.error(f"Error processing thank-you for {reg.get('id', 'unknown')}: {e}")
                continue
        
        if sent_count > 0:
            logger.info(f"Sent {sent_count} thank-you emails for events yesterday")
        return sent_count
        
    except Exception as e:
        logger.error(f"Error in process_thank_you_emails_for_yesterday: {e}")
        return 0


async def send_event_update_emails(event_id: str, changes: dict, new_event_data: dict):
    """Send update emails to ALL registered users when admin updates an upcoming event
    
    IMPORTANT: 
    - Update emails are sent to ALL registered users regardless of their email_status
    - Only sent for upcoming events (events in the future)
    - Only triggered when admin makes changes via the update endpoint
    
    Args:
        event_id: The event ID
        changes: Dictionary of changed fields with old and new values
                 e.g., {'date_time': {'old': '2024-01-01 10:00', 'new': '2024-01-02 14:00'}}
        new_event_data: The updated event data from database
    """
    try:
        supabase = get_supabase_client()
        
        # Get all registrations for this event (send updates to all registered users)
        query = lambda: (
            supabase
            .table("event_registrations")
            .select("""
                id,
                user_id,
                events!inner(
                    id,
                    title,
                    date_time,
                    location,
                    slug
                )
            """)
            .eq("event_id", event_id)
            .limit(500)
            .execute()
        )
        
        response = await safe_supabase_operation(query, "Failed to fetch registrations for event update")
        
        if not response.data:
            logger.info(f"No registrations found for event {event_id} to send update emails")
            return 0
        
        logger.info(f"Sending update emails to {len(response.data)} registered users for event {event_id}")
        
        sent_count = 0
        
        # Format event date and time from new event data
        event_date, event_time = format_datetime(new_event_data.get("date_time", ""))
        
        for reg in response.data:
            try:
                # Fetch user data
                user_query = lambda: (
                    supabase
                    .table("users")
                    .select("id, email, name")
                    .eq("id", reg["user_id"])
                    .limit(1)
                    .execute()
                )
                user_resp = await safe_supabase_operation(user_query, "Failed to fetch user")
                user_data = user_resp.data[0] if user_resp.data else None
                
                if not user_data:
                    admin_query = lambda: (
                        supabase
                        .table("admins")
                        .select("id, email, name")
                        .eq("id", reg["user_id"])
                        .limit(1)
                        .execute()
                    )
                    admin_resp = await safe_supabase_operation(admin_query, "Failed to fetch admin")
                    user_data = admin_resp.data[0] if admin_resp.data else None
                
                if not user_data or not user_data.get("email"):
                    continue
                
                event_data = reg.get("events") or new_event_data
                event_title = event_data.get("title", "Event")
                event_location = event_data.get("location", "TBA")
                event_slug = event_data.get("slug")
                
                result = await send_event_email(
                    email_type="update",
                    to_email=user_data["email"],
                    user_name=user_data.get("name", "Valued Member"),
                    event_title=event_title,
                    event_date=event_date,
                    event_time=event_time,
                    event_location=event_location,
                    event_slug=event_slug,
                    changes=changes
                )
                
                if result["success"]:
                    # Log the email
                    log_query = lambda: (
                        supabase
                        .table("email_logs")
                        .insert({
                            "registration_id": reg["id"],
                            "email_type": "update",
                            "recipient_email": user_data["email"],
                            "status": "sent",
                            "aws_message_id": result["message_id"]
                        })
                        .execute()
                    )
                    await safe_supabase_operation(log_query, "Failed to log update email")
                    
                    sent_count += 1
                    logger.info(f"Update email sent to {user_data['email']} for registration {reg['id']}")
                else:
                    logger.error(f"Failed to send update email to {user_data['email']}: {result['error']}")
                    
            except Exception as e:
                logger.error(f"Error sending update email for registration {reg.get('id', 'unknown')}: {e}")
                continue
        
        if sent_count > 0:
            logger.info(f"Sent {sent_count} update emails for event {event_id}")
        return sent_count
        
    except Exception as e:
        logger.error(f"Error in send_event_update_emails: {e}")
        return 0



