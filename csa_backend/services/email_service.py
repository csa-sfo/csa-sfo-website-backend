from models.request_models import ContactForm
from services.openai_service import run_openai_prompt
from config.settings import FROM_EMAIL, TO_EMAIL, MAILERSEND_API_KEY, FROM_NAME, OPENAI_MODEL
import logging
from pydantic import EmailStr
import logging, html2text
from mailersend import emails
import re
from typing import Optional, Dict, Any

# Create the client once – internal httpx session is re-used
_mailer = emails.NewEmail(MAILERSEND_API_KEY)

_FROM_EMAIL = FROM_EMAIL
_FROM_NAME  = FROM_NAME

# Debug: Check if API key is loaded


async def send_mailersend(
    *,
    subject: str,
    html_body: str,
    to_email: EmailStr,
) -> None:
    """
    Send an email via MailerSend SDK.
    Raises RuntimeError / ValueError from SDK on failure.
    """

    logging.info(f"MAILERSEND_API_KEY loaded: {'Yes' if MAILERSEND_API_KEY else 'No'}")
    if MAILERSEND_API_KEY:
        logging.info(f"API Key starts with: {MAILERSEND_API_KEY[:10]}...")
    mail = {}                                              # body container

    _mailer.set_mail_from({"email": _FROM_EMAIL,
                           "name":  _FROM_NAME}, mail)
    _mailer.set_mail_to([{"email": str(to_email)}], mail)
    _mailer.set_subject(subject, mail)
    _mailer.set_html_content(html_body, mail)

    # quick plaintext: HTML→text so Gmail dark-mode previews look sane
    _mailer.set_plaintext_content(
        html2text.html2text(html_body).strip(), mail
    )

    # Fire & forget – API returns 202 JSON on success
    resp = _mailer.send(mail)
    logging.info("MailerSend response: %s", resp)           # optional
    return resp




async def draft_email_body_html(form: ContactForm) -> str:
    """
    Ask GPT to return ONLY an HTML body (no <html> wrapper, no subject line).
    """
    system_prompt = (
        "You are a senior marketing assistant. Write a concise, friendly INTERNAL "
        "email in HTML that notifies the sales team about a new website enquiry. "
        "Requirements:\n"
        "• Do NOT include a subject line or emojis.\n"
        "• Start with a short greeting (e.g., 'Hi Team,').\n"
        "• Use an unordered list (<ul><li>) to show Name, Email, Company, Message.\n"
        "• End with a brief call-to-action (‘Please follow up…’) and a friendly sign-off as “Indrasol Sales”.\n"
        "Return ONLY the HTML snippet."
    )

    user_msg = (
        f"Name: {form.name}\n"
        f"Email: {form.email}\n"
        f"Company: {form.company or '—'}\n"
        f"Message: {form.message}"
    )

    html_body = await run_openai_prompt(
        prompt=user_msg,
        system_prompt=system_prompt,
        temperature=0.5,
        max_tokens=250,
        model=OPENAI_MODEL,
    )
    m = re.search(r"```(?:html)?\s*(.*?)```", html_body, re.DOTALL | re.IGNORECASE)
    html_body = m.group(1) if m else html_body
    return html_body.strip()


async def send_invoice_email(
    to_email: str,
    customer_name: str,
    amount: float,
    currency: str,
    product_name: str,
    payment_date: str,
    payment_id: str
) -> Dict[str, Any]:
    """
    Send an invoice email to the customer after successful payment.
    
    Args:
        to_email: Customer's email address
        customer_name: Customer's name
        amount: Total amount paid
        currency: Payment currency (e.g., 'USD')
        product_name: Name of the product/service purchased
        payment_date: Formatted date of payment
        payment_id: Payment reference ID
        
    Returns:
        Response from the email service
    """
    try:
        # Format amount with currency symbol
        amount_str = f"${amount:.2f}" if currency.lower() == 'usd' else f"{amount:.2f} {currency.upper()}"
        
        # Create email subject and body
        subject = f"Your Invoice for {product_name}"
        
        # Create HTML email content
        html_content = f"""
        <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ text-align: center; margin-bottom: 30px; }}
                    .logo {{ max-width: 200px; margin-bottom: 20px; }}
                    .content {{ background: #f9f9f9; padding: 20px; border-radius: 5px; }}
                    .footer {{ margin-top: 30px; font-size: 12px; color: #777; text-align: center; }}
                    .button {{
                        display: inline-block;
                        padding: 10px 20px;
                        background-color: #4CAF50;
                        color: white;
                        text-decoration: none;
                        border-radius: 5px;
                        margin: 15px 0;
                    }}
                    table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                    th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
                    th {{ background-color: #f2f2f2; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h2>Thank you for your payment!</h2>
                    </div>
                    
                    <div class="content">
                        <p>Dear {customer_name or 'Valued Customer'},</p>
                        
                        <p>We've received your payment for <strong>{product_name}</strong>.</p>
                        
                        <h3>Payment Details</h3>
                        <table>
                            <tr>
                                <th>Description</th>
                                <th>Amount</th>
                            </tr>
                            <tr>
                                <td>{product_name}</td>
                                <td>{amount_str}</td>
                            </tr>
                            <tr>
                                <td><strong>Total Paid</strong></td>
                                <td><strong>{amount_str}</strong></td>
                            </tr>
                        </table>
                        
                        <p><strong>Payment Date:</strong> {payment_date}</p>
                        <p><strong>Transaction ID:</strong> {payment_id}</p>
                        
                        <p>This email serves as your receipt. We appreciate your support!</p>
                        
                        <p>Best regards,<br>CSA San Francisco Chapter Team</p>
                    </div>
                    
                    <div class="footer">
                        <p>© {datetime.now().year} CSA San Francisco Chapter. All rights reserved.</p>
                        <p>This is an automated message. Please do not reply to this email.</p>
                    </div>
                </div>
            </body>
        </html>
        """.format(
            customer_name=customer_name or 'Valued Customer',
            product_name=product_name,
            amount_str=amount_str,
            payment_date=payment_date,
            payment_id=payment_id,
        )
        
        # Send the email
        response = await send_mailersend(
            to_email=to_email,
            subject=subject,
            html_body=html_content
        )
        
        logging.info(f"Invoice email sent to {to_email} for payment {payment_id}")
        return response
        
    except Exception as e:
        logging.error(f"Error sending invoice email: {str(e)}")
        raise

async def process_contact(form: ContactForm, is_bot: bool = True):
    try:
        html_body  = await draft_email_body_html(form)
        if is_bot:
            subject = (
                f"New Business Enquiry through IndraBot – {form.name}"
                    + (f" ({form.company})" if form.company else "")
            )
        else:
            subject = (
                f"New Business Enquiry through Contact US Form {form.name}"
                + (f" ({form.company})" if form.company else "")
            ) 
        # TO_EMAIL = TO_EMAIL
        await send_mailersend(
            subject=subject,
            html_body=html_body,
            to_email=TO_EMAIL,
        )
        logging.info(f"Contact email sent successfully to {TO_EMAIL}")
    except Exception as exc:
        logging.error("Failed to send contact email", exc_info=exc)
        raise  # Re-raise the exception so the caller can handle it