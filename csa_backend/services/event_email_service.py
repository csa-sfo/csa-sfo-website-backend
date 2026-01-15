"""
Service for sending event-related emails (confirmation, reminder, and thank-you) via AWS SES.
"""
import logging
from typing import Optional
from pydantic import EmailStr
from services.email_service import send_email
from services.event_email_templates import generate_confirmation_email, generate_reminder_email, generate_thank_you_email

logger = logging.getLogger(__name__)


async def send_confirmation_email(
    to_email: EmailStr,
    user_name: str,
    event_title: str,
    event_date_time: str,
    event_location: str,
    event_slug: Optional[str] = None,
) -> bool:
    """
    Send a confirmation email for a new event registration.
    
    Args:
        to_email: Recipient email address
        user_name: Name of the user
        event_title: Title of the event
        event_date_time: Event date and time (ISO format string)
        event_location: Location of the event
        event_slug: Optional slug for the event URL
        
    Returns:
        True if email was sent successfully, False otherwise
    """
    try:
        subject, html_body = generate_confirmation_email(
            user_name=user_name,
            event_title=event_title,
            event_date_time=event_date_time,
            event_location=event_location,
            event_slug=event_slug,
        )
        
        await send_email(
            subject=subject,
            html_body=html_body,
            to_email=to_email,
        )
        
        logger.info(f"Confirmation email sent successfully to {to_email} for event: {event_title}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send confirmation email to {to_email} for event {event_title}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


async def send_reminder_email(
    to_email: EmailStr,
    user_name: str,
    event_title: str,
    event_date_time: str,
    event_location: str,
    event_slug: Optional[str] = None,
) -> bool:
    """
    Send a reminder email for an event happening tomorrow.
    
    Args:
        to_email: Recipient email address
        user_name: Name of the user
        event_title: Title of the event
        event_date_time: Event date and time (ISO format string)
        event_location: Location of the event
        event_slug: Optional slug for the event URL
        
    Returns:
        True if email was sent successfully, False otherwise
    """
    try:
        subject, html_body = generate_reminder_email(
            user_name=user_name,
            event_title=event_title,
            event_date_time=event_date_time,
            event_location=event_location,
            event_slug=event_slug,
        )
        
        await send_email(
            subject=subject,
            html_body=html_body,
            to_email=to_email,
        )
        
        logger.info(f"Reminder email sent successfully to {to_email} for event: {event_title}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send reminder email to {to_email} for event {event_title}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


async def send_thank_you_email(
    to_email: EmailStr,
    user_name: str,
    event_title: str,
    event_date_time: str,
    event_location: str,
    event_slug: Optional[str] = None,
) -> bool:
    """
    Send a thank-you email for an event that was attended.
    
    Args:
        to_email: Recipient email address
        user_name: Name of the user
        event_title: Title of the event
        event_date_time: Event date and time (ISO format string)
        event_location: Location of the event
        event_slug: Optional slug for the event URL
        
    Returns:
        True if email was sent successfully, False otherwise
    """
    try:
        subject, html_body = generate_thank_you_email(
            user_name=user_name,
            event_title=event_title,
            event_date_time=event_date_time,
            event_location=event_location,
            event_slug=event_slug,
        )
        
        await send_email(
            subject=subject,
            html_body=html_body,
            to_email=to_email,
        )
        
        logger.info(f"Thank-you email sent successfully to {to_email} for event: {event_title}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send thank-you email to {to_email} for event {event_title}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

