"""
Event Email Service using AWS SES
Handles sending confirmation, reminder, and thank-you emails
"""
import boto3
from botocore.exceptions import ClientError
from typing import Optional, Dict, Any
import logging
from datetime import datetime
import os

from config.settings import (
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_REGION,
    AWS_SES_FROM_EMAIL,
    AWS_SES_FROM_NAME,
    FRONTEND_URL,
)
from services.event_email_templates import (
    generate_confirmation_email,
    generate_reminder_email,
    generate_thank_you_email,
)

logger = logging.getLogger(__name__)

# Initialize SES client
_ses_client = None

def get_ses_client():
    """Get or create AWS SES client"""
    global _ses_client
    if _ses_client is None:
        if not AWS_ACCESS_KEY_ID or not AWS_SECRET_ACCESS_KEY:
            raise Exception("AWS credentials not configured")
        
        _ses_client = boto3.client(
            'ses',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION or "us-east-1"
        )
    return _ses_client


async def send_event_email(
    email_type: str,  # 'confirmation', 'reminder', 'thank_you'
    to_email: str,
    user_name: str,
    event_title: str,
    event_date: str,
    event_time: Optional[str] = None,
    event_location: Optional[str] = None,
    event_slug: Optional[str] = None,
    frontend_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send event-related email via AWS SES
    
    Returns:
        dict with 'success' (bool), 'message_id' (str), 'error' (str)
    """
    try:
        ses_client = get_ses_client()
        
        # Use FRONTEND_URL from settings if not provided
        if frontend_url is None:
            frontend_url = FRONTEND_URL or "https://csasfo.com"
        
        # Generate email content based on type
        if email_type == 'confirmation':
            html_body, text_body = generate_confirmation_email(
                user_name=user_name,
                event_title=event_title,
                event_date=event_date,
                event_time=event_time or "TBA",
                event_location=event_location or "TBA",
                event_slug=event_slug,
                frontend_url=frontend_url
            )
            subject = f"RSVP Confirmed: {event_title}"
            
        elif email_type == 'reminder':
            html_body, text_body = generate_reminder_email(
                user_name=user_name,
                event_title=event_title,
                event_date=event_date,
                event_time=event_time or "TBA",
                event_location=event_location or "TBA",
                event_slug=event_slug,
                frontend_url=frontend_url
            )
            subject = f"Event Reminder: {event_title} Tomorrow"
            
        elif email_type == 'thank_you':
            html_body, text_body = generate_thank_you_email(
                user_name=user_name,
                event_title=event_title,
                event_date=event_date,
                event_time=event_time or "TBA",
                event_location=event_location or "TBA",
                event_slug=event_slug,
                frontend_url=frontend_url
            )
            subject = f"Thank You for Attending: {event_title}"
        else:
            raise ValueError(f"Invalid email_type: {email_type}")
        
        # Send email via SES
        from_email = AWS_SES_FROM_EMAIL or "noreply@csasfo.com"
        from_name = AWS_SES_FROM_NAME or "CSA San Francisco Chapter"
        
        response = ses_client.send_email(
            Source=f"{from_name} <{from_email}>",
            Destination={
                'ToAddresses': [to_email]
            },
            Message={
                'Subject': {
                    'Data': subject,
                    'Charset': 'UTF-8'
                },
                'Body': {
                    'Text': {
                        'Data': text_body,
                        'Charset': 'UTF-8'
                    },
                    'Html': {
                        'Data': html_body,
                        'Charset': 'UTF-8'
                    }
                }
            }
        )
        
        message_id = response.get('MessageId')
        logger.info(f"Email sent successfully: {email_type} to {to_email}, MessageId: {message_id}")
        
        return {
            'success': True,
            'message_id': message_id,
            'error': None
        }
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        logger.error(f"AWS SES error ({error_code}): {error_message}")
        return {
            'success': False,
            'message_id': None,
            'error': f"{error_code}: {error_message}"
        }
    except Exception as e:
        logger.error(f"Error sending {email_type} email: {str(e)}")
        return {
            'success': False,
            'message_id': None,
            'error': str(e)
        }


