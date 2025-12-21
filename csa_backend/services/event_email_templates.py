"""
HTML Email Templates for CSA SFO Event Notifications
Brand colors: #667eea (primary purple), #764ba2 (secondary purple)
Uses inline styles for maximum email client compatibility
"""
from datetime import datetime
from typing import Optional


def generate_confirmation_email(
    user_name: str,
    event_title: str,
    event_date: str,
    event_time: str,
    event_location: str,
    event_slug: Optional[str] = None,
    frontend_url: str = "https://csasfo.com"
) -> tuple[str, str]:
    """Generate RSVP Confirmation Email HTML and plain text"""
    
    event_url = f"{frontend_url}/events/{event_slug}" if event_slug else None
    
    html = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>RSVP Confirmed</title>
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; line-height: 1.6; color: #333333; background-color: #f5f5f5;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color: #f5f5f5; padding: 20px;">
    <tr>
      <td align="center">
        <table role="presentation" width="600" cellspacing="0" cellpadding="0" border="0" style="max-width: 600px; background: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);">
          <!-- Header -->
          <tr>
            <td bgcolor="#667eea" style="background-color: #667eea; color: #ffffff; padding: 40px 30px; text-align: center;">
              <div style="width: 60px; height: 60px; background-color: #5a6fd6; border-radius: 50%; margin: 0 auto 15px; line-height: 60px; font-size: 20px; font-weight: bold; color: #ffffff;">CSA</div>
              <h1 style="font-size: 28px; font-weight: 600; margin: 0; letter-spacing: -0.5px; color: #ffffff;">🎉 RSVP Confirmed!</h1>
            </td>
          </tr>
          
          <!-- Content -->
          <tr>
            <td style="padding: 40px 30px;">
              <p style="font-size: 18px; color: #333333; margin: 0 0 20px 0;">Dear {user_name or 'Valued Member'},</p>
              
              <p style="margin: 0 0 20px 0;">We're thrilled to confirm your registration for our upcoming event!</p>
              
              <!-- Event Card -->
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background: #f9f9f9; border-left: 4px solid #667eea; border-radius: 4px; margin: 25px 0;">
                <tr>
                  <td style="padding: 25px;">
                    <span style="display: inline-block; padding: 6px 12px; border-radius: 4px; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; background: #4CAF50; color: #ffffff;">✓ CONFIRMED</span>
                    <h2 style="font-size: 22px; font-weight: 600; color: #667eea; margin: 15px 0;">{event_title}</h2>
                    
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                      <tr>
                        <td style="padding: 12px 0; border-bottom: 1px solid #eeeeee;">
                          <span style="font-size: 18px; margin-right: 12px;">📅</span>
                          <span style="font-size: 12px; color: #666666; text-transform: uppercase; letter-spacing: 0.5px;">Date: </span>
                          <span style="font-size: 16px; color: #333333; font-weight: 500;">{event_date}</span>
                        </td>
                      </tr>
                      <tr>
                        <td style="padding: 12px 0; border-bottom: 1px solid #eeeeee;">
                          <span style="font-size: 18px; margin-right: 12px;">🕐</span>
                          <span style="font-size: 12px; color: #666666; text-transform: uppercase; letter-spacing: 0.5px;">Time: </span>
                          <span style="font-size: 16px; color: #333333; font-weight: 500;">{event_time}</span>
                        </td>
                      </tr>
                      <tr>
                        <td style="padding: 12px 0;">
                          <span style="font-size: 18px; margin-right: 12px;">📍</span>
                          <span style="font-size: 12px; color: #666666; text-transform: uppercase; letter-spacing: 0.5px;">Location: </span>
                          <span style="font-size: 16px; color: #333333; font-weight: 500;">{event_location}</span>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>
              
              <p style="margin: 0 0 20px 0;">We look forward to seeing you there! Please arrive a few minutes early for check-in and networking.</p>
              
              {f'''<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                <tr>
                  <td align="center" style="padding: 25px 0;">
                    <a href="{event_url}" style="display: inline-block; padding: 14px 32px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #ffffff; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 16px;">View Event Details</a>
                  </td>
                </tr>
              </table>''' if event_url else ''}
              
              <!-- Info Box -->
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background: #fff3cd; border-left: 4px solid #ffc107; border-radius: 4px; margin: 25px 0;">
                <tr>
                  <td style="padding: 20px;">
                    <h3 style="color: #856404; font-size: 16px; margin: 0 0 10px 0;">📋 What's Next?</h3>
                    <ul style="margin: 10px 0; padding-left: 20px; color: #856404;">
                      <li style="margin: 8px 0; font-size: 14px;">Add this event to your calendar</li>
                      <li style="margin: 8px 0; font-size: 14px;">Check your email for a reminder 24 hours before the event</li>
                      <li style="margin: 8px 0; font-size: 14px;">Follow us on social media for updates</li>
                    </ul>
                  </td>
                </tr>
              </table>
              
              <p style="margin: 0 0 20px 0;">If you have any questions or need to cancel your registration, please don't hesitate to contact us.</p>
              
              <p style="margin: 0;">Best regards,<br><strong>CSA San Francisco Chapter Team</strong></p>
            </td>
          </tr>
          
          <!-- Footer -->
          <tr>
            <td style="background: #f9f9f9; padding: 30px; text-align: center; border-top: 1px solid #eeeeee;">
              <p style="margin: 0 0 10px 0; font-size: 14px;"><strong>Cloud Security Alliance - San Francisco Chapter</strong></p>
              <p style="margin: 0; font-size: 12px; color: #666666;">This is an automated confirmation email. Please do not reply to this email.</p>
              <p style="margin: 10px 0 0 0; font-size: 12px; color: #999999;">© {datetime.now().year} CSA San Francisco. All rights reserved.</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
    """
    
    plain_text = f"""
RSVP Confirmed! 🎉

Dear {user_name or 'Valued Member'},

We're thrilled to confirm your registration for our upcoming event!

EVENT DETAILS
━━━━━━━━━━━━━
✓ CONFIRMED

{event_title}

📅 Date: {event_date}
🕐 Time: {event_time}
📍 Location: {event_location}

We look forward to seeing you there! Please arrive a few minutes early for check-in and networking.

{f"View Event: {event_url}" if event_url else ""}

WHAT'S NEXT?
• Add this event to your calendar
• Check your email for a reminder 24 hours before the event
• Follow us on social media for updates

If you have any questions or need to cancel your registration, please don't hesitate to contact us.

Best regards,
CSA San Francisco Chapter Team

---
Cloud Security Alliance - San Francisco Chapter
This is an automated confirmation email. Please do not reply to this email.
© {datetime.now().year} CSA San Francisco. All rights reserved.
    """
    
    return html.strip(), plain_text.strip()


def generate_reminder_email(
    user_name: str,
    event_title: str,
    event_date: str,
    event_time: str,
    event_location: str,
    event_slug: Optional[str] = None,
    frontend_url: str = "https://csasfo.com"
) -> tuple[str, str]:
    """Generate Event Reminder Email HTML and plain text (24 hours before)"""
    
    event_url = f"{frontend_url}/events/{event_slug}" if event_slug else None
    
    html = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Event Reminder</title>
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; line-height: 1.6; color: #333333; background-color: #f5f5f5;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color: #f5f5f5; padding: 20px;">
    <tr>
      <td align="center">
        <table role="presentation" width="600" cellspacing="0" cellpadding="0" border="0" style="max-width: 600px; background: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);">
          <!-- Header -->
          <tr>
            <td bgcolor="#667eea" style="background-color: #667eea; color: #ffffff; padding: 40px 30px; text-align: center;">
              <div style="width: 60px; height: 60px; background-color: #5a6fd6; border-radius: 50%; margin: 0 auto 15px; line-height: 60px; font-size: 20px; font-weight: bold; color: #ffffff;">CSA</div>
              <h1 style="font-size: 28px; font-weight: 600; margin: 0; letter-spacing: -0.5px; color: #ffffff;">⏰ Event Tomorrow!</h1>
            </td>
          </tr>
          
          <!-- Content -->
          <tr>
            <td style="padding: 40px 30px;">
              <p style="font-size: 18px; color: #333333; margin: 0 0 20px 0;">Dear {user_name or 'Valued Member'},</p>
              
              <p style="margin: 0 0 20px 0;">This is a friendly reminder that you're registered for an event <strong>tomorrow</strong>!</p>
              
              <!-- Event Card -->
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background: #f9f9f9; border-left: 4px solid #667eea; border-radius: 4px; margin: 25px 0;">
                <tr>
                  <td style="padding: 25px;">
                    <span style="display: inline-block; padding: 6px 12px; border-radius: 4px; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; background: #2196F3; color: #ffffff;">⏰ TOMORROW</span>
                    <h2 style="font-size: 22px; font-weight: 600; color: #667eea; margin: 15px 0;">{event_title}</h2>
                    
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                      <tr>
                        <td style="padding: 12px 0; border-bottom: 1px solid #eeeeee;">
                          <span style="font-size: 18px; margin-right: 12px;">📅</span>
                          <span style="font-size: 12px; color: #666666; text-transform: uppercase; letter-spacing: 0.5px;">Date: </span>
                          <span style="font-size: 16px; color: #333333; font-weight: 500;">{event_date}</span>
                        </td>
                      </tr>
                      <tr>
                        <td style="padding: 12px 0; border-bottom: 1px solid #eeeeee;">
                          <span style="font-size: 18px; margin-right: 12px;">🕐</span>
                          <span style="font-size: 12px; color: #666666; text-transform: uppercase; letter-spacing: 0.5px;">Time: </span>
                          <span style="font-size: 16px; color: #333333; font-weight: 500;">{event_time}</span>
                        </td>
                      </tr>
                      <tr>
                        <td style="padding: 12px 0;">
                          <span style="font-size: 18px; margin-right: 12px;">📍</span>
                          <span style="font-size: 12px; color: #666666; text-transform: uppercase; letter-spacing: 0.5px;">Location: </span>
                          <span style="font-size: 16px; color: #333333; font-weight: 500;">{event_location}</span>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>
              
              {f'''<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                <tr>
                  <td align="center" style="padding: 25px 0;">
                    <a href="{event_url}" style="display: inline-block; padding: 14px 32px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #ffffff; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 16px;">View Event Details</a>
                  </td>
                </tr>
              </table>''' if event_url else ''}
              
              <!-- Checklist -->
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background: #e8f5e9; border-left: 4px solid #4CAF50; border-radius: 4px; margin: 25px 0;">
                <tr>
                  <td style="padding: 20px;">
                    <h3 style="color: #2e7d32; font-size: 16px; margin: 0 0 10px 0;">✅ Pre-Event Checklist</h3>
                    <ul style="margin: 10px 0; padding-left: 20px; color: #2e7d32;">
                      <li style="margin: 8px 0; font-size: 14px;">Plan your route and parking</li>
                      <li style="margin: 8px 0; font-size: 14px;">Bring business cards for networking</li>
                      <li style="margin: 8px 0; font-size: 14px;">Arrive 10-15 minutes early</li>
                      <li style="margin: 8px 0; font-size: 14px;">Prepare questions for the speakers</li>
                    </ul>
                  </td>
                </tr>
              </table>
              
              <p style="margin: 0 0 20px 0;">We're excited to see you tomorrow! If you can no longer attend, please let us know so we can offer your spot to someone on the waitlist.</p>
              
              <p style="margin: 0;">See you soon!<br><strong>CSA San Francisco Chapter Team</strong></p>
            </td>
          </tr>
          
          <!-- Footer -->
          <tr>
            <td style="background: #f9f9f9; padding: 30px; text-align: center; border-top: 1px solid #eeeeee;">
              <p style="margin: 0 0 10px 0; font-size: 14px;"><strong>Cloud Security Alliance - San Francisco Chapter</strong></p>
              <p style="margin: 0; font-size: 12px; color: #666666;">This is an automated reminder email. Please do not reply to this email.</p>
              <p style="margin: 10px 0 0 0; font-size: 12px; color: #999999;">© {datetime.now().year} CSA San Francisco. All rights reserved.</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
    """
    
    plain_text = f"""
Event Tomorrow! ⏰

Dear {user_name or 'Valued Member'},

This is a friendly reminder that you're registered for an event TOMORROW!

EVENT DETAILS
━━━━━━━━━━━━━
⏰ TOMORROW

{event_title}

📅 Date: {event_date}
🕐 Time: {event_time}
📍 Location: {event_location}

{f"View Event: {event_url}" if event_url else ""}

PRE-EVENT CHECKLIST
✅ Plan your route and parking
✅ Bring business cards for networking
✅ Arrive 10-15 minutes early
✅ Prepare questions for the speakers

We're excited to see you tomorrow! If you can no longer attend, please let us know so we can offer your spot to someone on the waitlist.

See you soon!
CSA San Francisco Chapter Team

---
Cloud Security Alliance - San Francisco Chapter
This is an automated reminder email. Please do not reply to this email.
© {datetime.now().year} CSA San Francisco. All rights reserved.
    """
    
    return html.strip(), plain_text.strip()


def generate_thank_you_email(
    user_name: str,
    event_title: str,
    event_date: str,
    event_time: str,
    event_location: str,
    event_slug: Optional[str] = None,
    frontend_url: str = "https://csasfo.com"
) -> tuple[str, str]:
    """Generate Thank You Email HTML and plain text (24 hours after event)"""
    
    html = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Thank You for Attending</title>
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; line-height: 1.6; color: #333333; background-color: #f5f5f5;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color: #f5f5f5; padding: 20px;">
    <tr>
      <td align="center">
        <table role="presentation" width="600" cellspacing="0" cellpadding="0" border="0" style="max-width: 600px; background: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);">
          <!-- Header -->
          <tr>
            <td bgcolor="#667eea" style="background-color: #667eea; color: #ffffff; padding: 40px 30px; text-align: center;">
              <div style="width: 60px; height: 60px; background-color: #5a6fd6; border-radius: 50%; margin: 0 auto 15px; line-height: 60px; font-size: 20px; font-weight: bold; color: #ffffff;">CSA</div>
              <h1 style="font-size: 28px; font-weight: 600; margin: 0; letter-spacing: -0.5px; color: #ffffff;">🙏 Thank You!</h1>
            </td>
          </tr>
          
          <!-- Content -->
          <tr>
            <td style="padding: 40px 30px;">
              <p style="font-size: 18px; color: #333333; margin: 0 0 20px 0;">Dear {user_name or 'Valued Member'},</p>
              
              <p style="margin: 0 0 20px 0;">Thank you for attending our recent event! We hope you found it valuable and informative.</p>
              
              <!-- Event Card -->
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background: #f9f9f9; border-left: 4px solid #667eea; border-radius: 4px; margin: 25px 0;">
                <tr>
                  <td style="padding: 25px;">
                    <span style="display: inline-block; padding: 6px 12px; border-radius: 4px; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; background: #9C27B0; color: #ffffff;">✓ ATTENDED</span>
                    <h2 style="font-size: 22px; font-weight: 600; color: #667eea; margin: 15px 0;">{event_title}</h2>
                    
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                      <tr>
                        <td style="padding: 12px 0; border-bottom: 1px solid #eeeeee;">
                          <span style="font-size: 18px; margin-right: 12px;">📅</span>
                          <span style="font-size: 12px; color: #666666; text-transform: uppercase; letter-spacing: 0.5px;">Date: </span>
                          <span style="font-size: 16px; color: #333333; font-weight: 500;">{event_date}</span>
                        </td>
                      </tr>
                      <tr>
                        <td style="padding: 12px 0;">
                          <span style="font-size: 18px; margin-right: 12px;">📍</span>
                          <span style="font-size: 12px; color: #666666; text-transform: uppercase; letter-spacing: 0.5px;">Location: </span>
                          <span style="font-size: 16px; color: #333333; font-weight: 500;">{event_location}</span>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>
              
              <p style="margin: 0 0 20px 0;">Your participation helps make our community stronger. We value your engagement and look forward to seeing you at future events!</p>
              
              <!-- Upcoming Events CTA -->
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                <tr>
                  <td align="center" style="padding: 25px 0;">
                    <a href="{frontend_url}/events" style="display: inline-block; padding: 14px 32px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #ffffff; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 16px;">View Upcoming Events</a>
                  </td>
                </tr>
              </table>
              
              <!-- Stay Connected -->
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background: #e3f2fd; border-left: 4px solid #2196F3; border-radius: 4px; margin: 25px 0;">
                <tr>
                  <td style="padding: 20px;">
                    <h3 style="color: #1565c0; font-size: 16px; margin: 0 0 10px 0;">🔗 Stay Connected</h3>
                    <ul style="margin: 10px 0; padding-left: 20px; color: #1565c0;">
                      <li style="margin: 8px 0; font-size: 14px;">Follow us on LinkedIn for industry insights</li>
                      <li style="margin: 8px 0; font-size: 14px;">Check out our upcoming events</li>
                      <li style="margin: 8px 0; font-size: 14px;">Consider becoming a CSA member</li>
                    </ul>
                  </td>
                </tr>
              </table>
              
              <p style="margin: 0;">With gratitude,<br><strong>CSA San Francisco Chapter Team</strong></p>
            </td>
          </tr>
          
          <!-- Footer -->
          <tr>
            <td style="background: #f9f9f9; padding: 30px; text-align: center; border-top: 1px solid #eeeeee;">
              <p style="margin: 0 0 10px 0; font-size: 14px;"><strong>Cloud Security Alliance - San Francisco Chapter</strong></p>
              <p style="margin: 0; font-size: 12px; color: #666666;">This is an automated thank you email. Please do not reply to this email.</p>
              <p style="margin: 10px 0 0 0; font-size: 12px; color: #999999;">© {datetime.now().year} CSA San Francisco. All rights reserved.</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
    """
    
    plain_text = f"""
Thank You for Attending! 🙏

Dear {user_name or 'Valued Member'},

Thank you for attending our recent event! We hope you found it valuable and informative.

EVENT ATTENDED
━━━━━━━━━━━━━━
✓ ATTENDED

{event_title}

📅 Date: {event_date}
📍 Location: {event_location}

Your participation helps make our community stronger. We value your engagement and look forward to seeing you at future events!

View Upcoming Events: {frontend_url}/events

STAY CONNECTED
🔗 Follow us on LinkedIn for industry insights
🔗 Check out our upcoming events
🔗 Consider becoming a CSA member

With gratitude,
CSA San Francisco Chapter Team

---
Cloud Security Alliance - San Francisco Chapter
This is an automated thank you email. Please do not reply to this email.
© {datetime.now().year} CSA San Francisco. All rights reserved.
    """
    
    return html.strip(), plain_text.strip()
