"""
Email templates for event-related emails (confirmation, reminder, and thank-you).
"""
from typing import Optional
import os
import pytz

# Get frontend URL from environment or use default
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://csasfo.com")

# Pacific Time zone (handles both PST and PDT automatically)
PACIFIC_TZ = pytz.timezone("America/Los_Angeles")


def generate_confirmation_email(
    user_name: str,
    event_title: str,
    event_date_time: str,
    event_location: str,
    event_slug: Optional[str] = None,
) -> tuple[str, str]:
    """
    Generate confirmation email HTML and subject for a new event registration.
    
    Args:
        user_name: Name of the user
        event_title: Title of the event
        event_date_time: Event date and time (ISO format string)
        event_location: Location of the event
        event_slug: Optional slug for the event URL
        
    Returns:
        Tuple of (subject, html_body)
    """
    # Format the date/time for display in Pacific Time
    try:
        from datetime import datetime
        # Parse the datetime (assume UTC if no timezone)
        dt = datetime.fromisoformat(event_date_time.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt)
        else:
            dt = dt.astimezone(pytz.UTC)
        
        # Convert to Pacific Time
        dt_pacific = dt.astimezone(PACIFIC_TZ)
        formatted_date = dt_pacific.strftime("%A, %B %d, %Y")
        formatted_time = dt_pacific.strftime("%I:%M %p %Z")
    except Exception:
        formatted_date = event_date_time
        formatted_time = ""
    
    # Build event URL
    if event_slug:
        event_url = f"{FRONTEND_URL}/events/{event_slug}"
    else:
        event_url = f"{FRONTEND_URL}/events"
    
    subject = f"✅ Registration Confirmed: {event_title}"
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{subject}</title>
    </head>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
            <h1 style="color: white; margin: 0; font-size: 28px;">Registration Confirmed!</h1>
        </div>
        
        <div style="background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px;">
            <p style="font-size: 16px; margin-bottom: 20px;">Hi {user_name},</p>
            
            <p style="font-size: 16px; margin-bottom: 20px;">
                Great news! Your registration for <strong>{event_title}</strong> has been confirmed.
            </p>
            
            <div style="background: white; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #28a745;">
                <h2 style="margin-top: 0; color: #28a745;">Event Details</h2>
                <p style="margin: 10px 0;"><strong>📅 Date:</strong> {formatted_date}</p>
                <p style="margin: 10px 0;"><strong>🕐 Time:</strong> {formatted_time}</p>
                <p style="margin: 10px 0;"><strong>📍 Location:</strong> {event_location}</p>
            </div>
            
            <div style="background: #d4edda; padding: 15px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #28a745;">
                <p style="margin: 0; font-size: 14px;">
                    <strong>📧 What's Next?</strong> You'll receive a reminder email the day before the event with all the details you need.
                </p>
            </div>
            
            <div style="text-align: center; margin: 30px 0;">
                <a href="{event_url}" 
                   style="display: inline-block; padding: 12px 30px; background-color: #28a745; color: white; text-decoration: none; border-radius: 5px; font-weight: bold;">
                    View Event Details
                </a>
            </div>
            
            <p style="font-size: 14px; color: #666; margin-top: 30px;">
                We look forward to seeing you there!
            </p>
            
            <p style="font-size: 14px; color: #666; margin-top: 20px;">
                Best regards,<br>
                <strong>CSA San Francisco Chapter</strong>
            </p>
        </div>
        
        <div style="text-align: center; margin-top: 20px; padding: 20px; color: #999; font-size: 12px;">
            <p>This is an automated confirmation email. If you have any questions, please contact us.</p>
        </div>
    </body>
    </html>
    """
    
    return subject, html_body


def generate_reminder_email(
    user_name: str,
    event_title: str,
    event_date_time: str,
    event_location: str,
    event_slug: Optional[str] = None,
) -> tuple[str, str]:
    """
    Generate reminder email HTML and subject for an event happening tomorrow.
    
    Args:
        user_name: Name of the user
        event_title: Title of the event
        event_date_time: Event date and time (ISO format string)
        event_location: Location of the event
        event_slug: Optional slug for the event URL
        
    Returns:
        Tuple of (subject, html_body)
    """
    # Format the date/time for display in Pacific Time
    try:
        from datetime import datetime
        # Parse the datetime (assume UTC if no timezone)
        dt = datetime.fromisoformat(event_date_time.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt)
        else:
            dt = dt.astimezone(pytz.UTC)
        
        # Convert to Pacific Time
        dt_pacific = dt.astimezone(PACIFIC_TZ)
        formatted_date = dt_pacific.strftime("%A, %B %d, %Y")
        formatted_time = dt_pacific.strftime("%I:%M %p %Z")
    except Exception:
        formatted_date = event_date_time
        formatted_time = ""
    
    # Build event URL
    if event_slug:
        event_url = f"{FRONTEND_URL}/events/{event_slug}"
    else:
        event_url = f"{FRONTEND_URL}/events"
    
    subject = f"⏰ Reminder: {event_title} Tomorrow!"
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{subject}</title>
    </head>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
            <h1 style="color: white; margin: 0; font-size: 28px;">Event Reminder</h1>
        </div>
        
        <div style="background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px;">
            <p style="font-size: 16px; margin-bottom: 20px;">Hi {user_name},</p>
            
            <p style="font-size: 16px; margin-bottom: 20px;">
                This is a friendly reminder that you're registered for <strong>{event_title}</strong>, which is happening <strong>tomorrow</strong>!
            </p>
            
            <div style="background: white; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #667eea;">
                <h2 style="margin-top: 0; color: #667eea;">Event Details</h2>
                <p style="margin: 10px 0;"><strong>📅 Date:</strong> {formatted_date}</p>
                <p style="margin: 10px 0;"><strong>🕐 Time:</strong> {formatted_time}</p>
                <p style="margin: 10px 0;"><strong>📍 Location:</strong> {event_location}</p>
            </div>
            
            <div style="text-align: center; margin: 30px 0;">
                <a href="{event_url}" 
                   style="display: inline-block; padding: 12px 30px; background-color: #667eea; color: white; text-decoration: none; border-radius: 5px; font-weight: bold;">
                    View Event Details
                </a>
            </div>
            
            <p style="font-size: 14px; color: #666; margin-top: 30px;">
                We look forward to seeing you there!
            </p>
            
            <p style="font-size: 14px; color: #666; margin-top: 20px;">
                Best regards,<br>
                <strong>CSA San Francisco Chapter</strong>
            </p>
        </div>
        
        <div style="text-align: center; margin-top: 20px; padding: 20px; color: #999; font-size: 12px;">
            <p>This is an automated reminder email. If you have any questions, please contact us.</p>
        </div>
    </body>
    </html>
    """
    
    return subject, html_body


def generate_thank_you_email(
    user_name: str,
    event_title: str,
    event_date_time: str,
    event_location: str,
    event_slug: Optional[str] = None,
) -> tuple[str, str]:
    """
    Generate thank-you email HTML and subject for an event that was attended.
    
    Args:
        user_name: Name of the user
        event_title: Title of the event
        event_date_time: Event date and time (ISO format string)
        event_location: Location of the event
        event_slug: Optional slug for the event URL
        
    Returns:
        Tuple of (subject, html_body)
    """
    # Format the date/time for display in Pacific Time
    try:
        from datetime import datetime
        # Parse the datetime (assume UTC if no timezone)
        dt = datetime.fromisoformat(event_date_time.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt)
        else:
            dt = dt.astimezone(pytz.UTC)
        
        # Convert to Pacific Time
        dt_pacific = dt.astimezone(PACIFIC_TZ)
        formatted_date = dt_pacific.strftime("%A, %B %d, %Y")
    except Exception:
        formatted_date = event_date_time
    
    # Build event URL
    if event_slug:
        event_url = f"{FRONTEND_URL}/events/{event_slug}"
    else:
        event_url = f"{FRONTEND_URL}/events"
    
    subject = f"Thank You for Attending: {event_title}"
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{subject}</title>
    </head>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
            <h1 style="color: white; margin: 0; font-size: 28px;">Thank You!</h1>
        </div>
        
        <div style="background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px;">
            <p style="font-size: 16px; margin-bottom: 20px;">Hi {user_name},</p>
            
            <p style="font-size: 16px; margin-bottom: 20px;">
                Thank you for attending <strong>{event_title}</strong> on {formatted_date}!
            </p>
            
            <p style="font-size: 16px; margin-bottom: 20px;">
                We hope you had a great time and found the event valuable. Your participation helps make our community stronger.
            </p>
            
            <div style="background: white; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #667eea;">
                <h2 style="margin-top: 0; color: #667eea;">Event Summary</h2>
                <p style="margin: 10px 0;"><strong>📅 Event:</strong> {event_title}</p>
                <p style="margin: 10px 0;"><strong>📅 Date:</strong> {formatted_date}</p>
                <p style="margin: 10px 0;"><strong>📍 Location:</strong> {event_location}</p>
            </div>
            
            <div style="background: #fff3cd; padding: 15px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #ffc107;">
                <p style="margin: 0; font-size: 14px;">
                    <strong>💬 We'd love your feedback!</strong> If you have a moment, please share your thoughts about the event. Your feedback helps us improve future events.
                </p>
            </div>
            
            <div style="text-align: center; margin: 30px 0;">
                <a href="{event_url}" 
                   style="display: inline-block; padding: 12px 30px; background-color: #667eea; color: white; text-decoration: none; border-radius: 5px; font-weight: bold;">
                    View Event Page
                </a>
            </div>
            
            <p style="font-size: 14px; color: #666; margin-top: 30px;">
                We look forward to seeing you at future events!
            </p>
            
            <p style="font-size: 14px; color: #666; margin-top: 20px;">
                Best regards,<br>
                <strong>CSA San Francisco Chapter</strong>
            </p>
        </div>
        
        <div style="text-align: center; margin-top: 20px; padding: 20px; color: #999; font-size: 12px;">
            <p>This is an automated thank-you email. If you have any questions, please contact us.</p>
        </div>
    </body>
    </html>
    """
    
    return subject, html_body

