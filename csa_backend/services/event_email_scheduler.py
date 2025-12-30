"""
Email Automation Scheduler for Event Notifications
Handles edge cases like late registrations (< 24h before event)
Works with existing event_registrations table schema
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import pytz

from db.supabase import get_supabase_client, safe_supabase_operation
from services.event_email_service import send_event_email

logger = logging.getLogger(__name__)

TIMEZONE = pytz.timezone("America/Los_Angeles")
MIN_REMINDER_HOURS = 0  # Allow reminders even if event is very close (0 = no minimum)

# Global scheduler reference (set by main.py)
scheduler: Optional[Any] = None


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
                
                # Send confirmation email
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
                    # Always just send confirmation - reminders handled separately by scheduler 24h before event
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


async def process_reminder_emails():
    """Send reminder emails approximately 24 hours before event start
    
    Only processes registrations that:
    - Have confirmation_sent status
    - Event is between 22-26 hours away (wider window to catch reminders)
    - Reminder hasn't been sent yet (reminder_sent_at IS NULL)
    """
    try:
        supabase = get_supabase_client()
        now = datetime.now(TIMEZONE)
        now_utc = now.astimezone(pytz.UTC)
        
        # Calculate reminder window in UTC - wider window around 24 hours
        # 22-26 hours gives us a 2-hour buffer on each side to catch reminders
        reminder_window_start_utc = (now_utc + timedelta(hours=22)).isoformat()
        reminder_window_end_utc = (now_utc + timedelta(hours=26)).isoformat()
        
        logger.debug(f"Checking for reminders: events starting between {reminder_window_start_utc} and {reminder_window_end_utc}")
        
        # Fetch all candidates (filter by status, then check timing in Python for accuracy)
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
            .limit(200)
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
                
                # Check timing - must be exactly 24 hours before event (23.5-24.5 hour window)
                event_start = datetime.fromisoformat(
                    event_data["date_time"].replace('Z', '+00:00')
                )
                if event_start.tzinfo is None:
                    event_start = pytz.UTC.localize(event_start)
                event_start_local = event_start.astimezone(TIMEZONE)
                hours_until_event = (event_start_local - now).total_seconds() / 3600
                
                # Skip if too close (< 2h) - too late to send reminder
                if hours_until_event < MIN_REMINDER_HOURS:
                    logger.debug(
                        f"Skipping reminder for {reg['id']}: event is {hours_until_event:.1f}h away (too soon)"
                    )
                    continue
                
                # Only send if event is 22-26 hours away (wider window to catch reminders)
                # This ensures we don't miss reminders if the periodic check runs slightly off-schedule
                if hours_until_event < 22 or hours_until_event > 26:
                    logger.debug(
                        f"Skipping reminder for {reg['id']}: event is {hours_until_event:.1f}h away (need 22-26h, will check again later)"
                    )
                    continue
                
                logger.info(
                    f"Processing reminder for {reg['id']}: event '{event_data['title']}' is {hours_until_event:.1f}h away"
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
                    logger.info(f"Reminder sent for registration {reg['id']} ({hours_until_event:.1f}h before event)")
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
            logger.info(f"Sent {sent_count} reminder emails")
        return sent_count
        
    except Exception as e:
        logger.error(f"Error in process_reminder_emails: {e}")
        return 0


async def process_thank_you_emails():
    """Send thank-you emails exactly 24 hours after event start time"""
    try:
        supabase = get_supabase_client()
        now = datetime.now(TIMEZONE)
        
        # Target: events that started exactly 24 hours ago (23.5-24.5 hour window)
        # This gives us 30 min buffer on each side since scheduler runs every 15 min
        target_time = now - timedelta(hours=24)
        start_window = target_time - timedelta(minutes=30)  # 23.5 hours ago
        end_window = target_time + timedelta(minutes=30)   # 24.5 hours ago
        
        logger.debug(f"Checking for thank-you emails: events that started between {start_window.isoformat()} and {end_window.isoformat()}")
        
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
            .limit(100)
            .execute()
        )
        
        response = await safe_supabase_operation(query, "Failed to fetch thank-you candidates")
        
        if not response.data:
            return 0
        
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
                
                # Calculate hours since event started
                hours_since_event = (now - event_start_local).total_seconds() / 3600
                
                # Only send if event started 23.5-24.5 hours ago (tight window around 24h)
                if hours_since_event < 23.5 or hours_since_event > 24.5:
                    logger.debug(
                        f"Skipping thank-you for {reg['id']}: event started {hours_since_event:.1f}h ago (need 23.5-24.5h, will check again later)"
                    )
                    continue
                
                logger.info(
                    f"Processing thank-you for {reg['id']}: event '{event_data['title']}' started {hours_since_event:.1f}h ago"
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
                
                event_date, _ = format_datetime(event_data["date_time"])
                
                result = await send_event_email(
                    email_type="thank_you",
                    to_email=user_data["email"],
                    user_name=user_data.get("name", "Valued Member"),
                    event_title=event_data["title"],
                    event_date=event_date
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
                    logger.info(f"Thank-you sent for registration {reg['id']} ({hours_since_event:.1f}h after event start)")
                    
            except Exception as e:
                logger.error(f"Error processing thank-you for {reg.get('id', 'unknown')}: {e}")
                continue
        
        if sent_count > 0:
            logger.info(f"Sent {sent_count} thank-you emails")
        return sent_count
        
    except Exception as e:
        logger.error(f"Error in process_thank_you_emails: {e}")
        return 0


async def reschedule_reminders_for_event(event_id: str, new_event_time: datetime):
    """Reschedule all reminder and thank-you jobs for an event when event time changes"""
    try:
        if scheduler is None:
            logger.warning("Scheduler not available, cannot reschedule emails")
            return 0
        
        supabase = get_supabase_client()
        timezone = pytz.timezone("America/Los_Angeles")
        
        # Convert new event time to local timezone
        if new_event_time.tzinfo is None:
            new_event_time = pytz.UTC.localize(new_event_time)
        new_event_time_local = new_event_time.astimezone(timezone)
        
        # Get all registrations for this event
        query = lambda: (
            supabase
            .table("event_registrations")
            .select("id, email_status, reminder_sent_at, thank_you_sent_at")
            .eq("event_id", event_id)
            .in_("email_status", ["confirmation_sent", "reminder_sent"])
            .execute()
        )
        
        response = await safe_supabase_operation(query, "Failed to fetch registrations")
        
        if not response.data:
            logger.info(f"No registrations to reschedule for event {event_id}")
            return 0
        
        rescheduled_reminders = 0
        rescheduled_thank_yous = 0
        now = datetime.now(timezone)
        reminder_time = new_event_time_local - timedelta(hours=24)
        thank_you_time = new_event_time_local + timedelta(hours=24)
        
        for reg in response.data:
            registration_id = reg["id"]
            
            # Reschedule reminder job if not sent yet
            if reg.get("reminder_sent_at") is None and reminder_time > now:
                reminder_job_id = f'reminder_{registration_id}'
                try:
                    # Remove old job if it exists
                    try:
                        scheduler.remove_job(reminder_job_id)
                        logger.debug(f"Removed old reminder job {reminder_job_id}")
                    except Exception:
                        pass
                    
                    # Schedule new reminder job
                    from apscheduler.triggers.date import DateTrigger
                    import asyncio
                    
                    scheduler.add_job(
                        lambda rid=registration_id: asyncio.run(send_reminder_for_registration(rid)),
                        trigger=DateTrigger(run_date=reminder_time),
                        id=reminder_job_id,
                        replace_existing=True
                    )
                    rescheduled_reminders += 1
                    logger.info(f"Rescheduled reminder for registration {registration_id} to {reminder_time}")
                except Exception as e:
                    logger.error(f"Failed to reschedule reminder for registration {registration_id}: {e}")
            
            # Reschedule thank-you job if not sent yet
            if reg.get("thank_you_sent_at") is None and thank_you_time > now:
                thank_you_job_id = f'thank_you_{registration_id}'
                try:
                    # Remove old job if it exists
                    try:
                        scheduler.remove_job(thank_you_job_id)
                        logger.debug(f"Removed old thank-you job {thank_you_job_id}")
                    except Exception:
                        pass
                    
                    # Schedule new thank-you job
                    from apscheduler.triggers.date import DateTrigger
                    import asyncio
                    
                    scheduler.add_job(
                        lambda rid=registration_id: asyncio.run(send_thank_you_for_registration(rid)),
                        trigger=DateTrigger(run_date=thank_you_time),
                        id=thank_you_job_id,
                        replace_existing=True
                    )
                    rescheduled_thank_yous += 1
                    logger.info(f"Rescheduled thank-you for registration {registration_id} to {thank_you_time}")
                except Exception as e:
                    logger.error(f"Failed to reschedule thank-you for registration {registration_id}: {e}")
        
        total_rescheduled = rescheduled_reminders + rescheduled_thank_yous
        logger.info(f"Rescheduled {rescheduled_reminders} reminder jobs and {rescheduled_thank_yous} thank-you jobs for event {event_id}")
        return total_rescheduled
        
    except Exception as e:
        logger.error(f"Error rescheduling emails for event {event_id}: {e}")
        return 0


async def reschedule_pending_reminders():
    """Re-schedule reminder jobs for all registrations that haven't received reminders yet.
    Useful after server restart or when switching from MemoryJobStore to persistent storage.
    """
    try:
        if scheduler is None:
            logger.warning("Scheduler not available, cannot reschedule reminders")
            return 0
        
        supabase = get_supabase_client()
        now = datetime.now(TIMEZONE)
        
        # Get all registrations that need reminders
        query = lambda: (
            supabase
            .table("event_registrations")
            .select("""
                id,
                event_id,
                events!inner(
                    id,
                    date_time
                )
            """)
            .eq("email_status", "confirmation_sent")
            .is_("reminder_sent_at", "null")
            .limit(500)
            .execute()
        )
        
        response = await safe_supabase_operation(query, "Failed to fetch pending reminders")
        
        if not response.data:
            return 0
        
        logger.info(f"Rescheduling reminders for {len(response.data)} registrations")
        
        rescheduled_count = 0
        from apscheduler.triggers.date import DateTrigger
        import asyncio
        
        for reg in response.data:
            try:
                registration_id = reg["id"]
                event_data = reg.get("events")
                
                if not event_data:
                    continue
                
                # Calculate reminder time
                event_start = datetime.fromisoformat(
                    event_data["date_time"].replace('Z', '+00:00')
                )
                if event_start.tzinfo is None:
                    event_start = pytz.UTC.localize(event_start)
                event_start_local = event_start.astimezone(TIMEZONE)
                reminder_time = event_start_local - timedelta(hours=24)
                
                # Only schedule if reminder time is in the future and event is more than 2 hours away
                hours_until_event = (event_start_local - now).total_seconds() / 3600
                if reminder_time > now and hours_until_event > MIN_REMINDER_HOURS:
                    reminder_job_id = f'reminder_{registration_id}'
                    
                    # Remove old job if it exists
                    try:
                        scheduler.remove_job(reminder_job_id)
                    except Exception:
                        pass
                    
                    # Schedule new reminder job
                    scheduler.add_job(
                        lambda rid=registration_id: asyncio.run(send_reminder_for_registration(rid)),
                        trigger=DateTrigger(run_date=reminder_time),
                        id=reminder_job_id,
                        replace_existing=True
                    )
                    rescheduled_count += 1
                    logger.debug(f"Rescheduled reminder for registration {registration_id} at {reminder_time}")
            except Exception as e:
                logger.error(f"Error rescheduling reminder for registration {reg.get('id', 'unknown')}: {e}")
                continue
        
        if rescheduled_count > 0:
            logger.info(f"Rescheduled {rescheduled_count} reminder jobs")
        return rescheduled_count
        
    except Exception as e:
        logger.error(f"Error in reschedule_pending_reminders: {e}")
        return 0


async def send_thank_you_for_registration(registration_id: str):
    """Send thank-you email for a specific registration (called by scheduled job)"""
    logger.debug(f"Thank-you job executed for registration {registration_id}")
    try:
        supabase = get_supabase_client()
        
        # Fetch registration with event and user data
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
            .eq("id", registration_id)
            .in_("email_status", ["confirmation_sent", "reminder_sent"])
            .is_("thank_you_sent_at", "null")
            .limit(1)
            .execute()
        )
        
        response = await safe_supabase_operation(query, "Failed to fetch registration")
        
        if not response.data:
            logger.warning(f"Registration {registration_id} not found or thank-you already sent")
            return False
        
        reg = response.data[0]
        event_data = reg.get("events")
        
        if not event_data:
            logger.warning(f"No event data for registration {registration_id}")
            return False
        
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
            logger.warning(f"No email found for registration {registration_id}")
            return False
        
        # Safety check: Verify event started approximately 24 hours ago
        # This handles cases where event time was changed after job was scheduled
        event_start = datetime.fromisoformat(
            event_data["date_time"].replace('Z', '+00:00')
        )
        if event_start.tzinfo is None:
            event_start = pytz.UTC.localize(event_start)
        event_start_local = event_start.astimezone(TIMEZONE)
        now = datetime.now(TIMEZONE)
        hours_since_event = (now - event_start_local).total_seconds() / 3600
        
        # Safety check: Only send if event started 22-26 hours ago (wider window for safety)
        if hours_since_event < 22 or hours_since_event > 26:
            logger.warning(
                f"Event time may have changed for registration {registration_id}. "
                f"Event started {hours_since_event:.1f}h ago (expected ~24h). Skipping thank-you."
            )
            return False
        
        logger.debug(f"Sending thank-you for registration {registration_id} ({hours_since_event:.1f}h after event)")
        
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
                .eq("id", registration_id)
                .execute()
            )
            await safe_supabase_operation(update_query, "Failed to update thank-you")
            
            log_query = lambda: (
                supabase
                .table("email_logs")
                .insert({
                    "registration_id": registration_id,
                    "email_type": "thank_you",
                    "recipient_email": user_data["email"],
                    "status": "sent",
                    "aws_message_id": result["message_id"]
                })
                .execute()
            )
            await safe_supabase_operation(log_query, "Failed to log thank-you")
            
            logger.info(f"Thank-you sent for registration {registration_id}")
            return True
        else:
            logger.error(f"Failed to send thank-you for {registration_id}: {result['error']}")
            # Update error but keep status
            update_query = lambda: (
                supabase
                .table("event_registrations")
                .update({
                    "email_error": f"Thank-you failed: {result['error']}"
                })
                .eq("id", registration_id)
                .execute()
            )
            await safe_supabase_operation(update_query, "Failed to update error")
            return False
            
    except Exception as e:
        logger.error(f"Error sending thank-you for registration {registration_id}: {e}")
        return False


async def send_reminder_for_registration(registration_id: str):
    """Send reminder email for a specific registration (called by scheduled job)"""
    logger.debug(f"Reminder job executed for registration {registration_id}")
    try:
        supabase = get_supabase_client()
        
        # Fetch registration with event and user data
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
            .eq("id", registration_id)
            .eq("email_status", "confirmation_sent")
            .is_("reminder_sent_at", "null")
            .limit(1)
            .execute()
        )
        
        response = await safe_supabase_operation(query, "Failed to fetch registration")
        
        if not response.data:
            logger.warning(f"Registration {registration_id} not found or reminder already sent")
            return False
        
        reg = response.data[0]
        event_data = reg.get("events")
        
        if not event_data:
            logger.warning(f"No event data for registration {registration_id}")
            return False
        
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
            logger.warning(f"No email found for registration {registration_id}")
            return False
        
        # Safety check: Verify event time is still approximately 24 hours away
        # This handles cases where event time was changed after job was scheduled
        event_start = datetime.fromisoformat(
            event_data["date_time"].replace('Z', '+00:00')
        )
        if event_start.tzinfo is None:
            event_start = pytz.UTC.localize(event_start)
        event_start_local = event_start.astimezone(TIMEZONE)
        now = datetime.now(TIMEZONE)
        hours_until_event = (event_start_local - now).total_seconds() / 3600
        
        # Safety check: Verify event is still in reasonable window (22-26 hours)
        # This handles cases where event time was changed after job was scheduled
        # Wider window to account for job execution timing variations
        if hours_until_event < 22 or hours_until_event > 26:
            logger.warning(
                f"Event time may have changed for registration {registration_id}. "
                f"Event is {hours_until_event:.1f}h away (expected ~24h). Skipping reminder."
            )
            return False
        
        logger.debug(f"Sending reminder for registration {registration_id} ({hours_until_event:.1f}h before event)")
        
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
                .eq("id", registration_id)
                .execute()
            )
            await safe_supabase_operation(update_query, "Failed to update reminder")
            
            log_query = lambda: (
                supabase
                .table("email_logs")
                .insert({
                    "registration_id": registration_id,
                    "email_type": "reminder",
                    "recipient_email": user_data["email"],
                    "status": "sent",
                    "aws_message_id": result["message_id"]
                })
                .execute()
            )
            await safe_supabase_operation(log_query, "Failed to log reminder")
            
            logger.info(f"Reminder sent for registration {registration_id}")
            return True
        else:
            logger.error(f"Failed to send reminder for {registration_id}: {result['error']}")
            # Update error but keep status as confirmation_sent
            update_query = lambda: (
                supabase
                .table("event_registrations")
                .update({
                    "email_error": f"Reminder failed: {result['error']}"
                })
                .eq("id", registration_id)
                .execute()
            )
            await safe_supabase_operation(update_query, "Failed to update error")
            return False
            
    except Exception as e:
        logger.error(f"Error sending reminder for registration {registration_id}: {e}")
        return False


async def run_email_automation():
    """Main function to run all email automation tasks"""
    logger.info("Starting email automation job...")
    
    confirmations = await process_pending_confirmations()
    reminders = await process_reminder_emails()
    thank_yous = await process_thank_you_emails()
    
    logger.info(
        f"Email automation completed: "
        f"{confirmations} confirmations, {reminders} reminders, {thank_yous} thank-yous"
    )
    
    return {
        "confirmations": confirmations,
        "reminders": reminders,
        "thank_yous": thank_yous
    }

