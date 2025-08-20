from fastapi import APIRouter, HTTPException, BackgroundTasks, Request, Depends, status, Query
from fastapi.responses import JSONResponse, RedirectResponse
from config.logging import setup_logging
import logging
import stripe
import os
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pydantic import BaseModel
from dotenv import load_dotenv
from config.settings import STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET

# Import Supabase service
from services.supabase_service import safe_supabase_operation
from db.supabase import get_supabase_client

# Load environment variables
load_dotenv()

# Configure Stripe
stripe.api_key = STRIPE_SECRET_KEY
webhook_secret = STRIPE_WEBHOOK_SECRET

# Initialize logger
setup_logging()
logger = logging.getLogger(__name__)

payment_router = APIRouter(prefix="/payments", tags=["payments"])

# Request models
class CreateCheckoutSession(BaseModel):
    price_id: str
    customer_email: str
    success_url: str
    cancel_url: str
    customer_name: Optional[str] = None
    metadata: Optional[dict] = None

@payment_router.post("/create-checkout-session")
async def create_checkout_session(data: CreateCheckoutSession):
    try:
        # First, create a customer if they don't exist
        customer = stripe.Customer.create(
            email=data.customer_email,
            name=data.customer_name or data.customer_email.split('@')[0],
            metadata={
                'source': 'website_checkout',
                **(data.metadata or {})
            }
        )
        
        # Create checkout session with invoice creation enabled
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': data.price_id,
                'quantity': 1,
            }],
            mode='payment',
            customer=customer.id,
            success_url=data.success_url,
            cancel_url=data.cancel_url,
            metadata=data.metadata or {},
            invoice_creation={
                'enabled': True,
            },
            payment_intent_data={
                'setup_future_usage': 'off_session',
                'metadata': data.metadata or {}
            },
            automatic_tax={
                'enabled': False,  # Disabled to avoid origin address requirement in test mode
            },
            tax_id_collection={
                'enabled': False,  # Disabled since automatic tax is off
            },
            allow_promotion_codes=False,
            billing_address_collection='auto',  # Changed from 'required' to 'auto' to be less restrictive
            submit_type='pay',
        )
        
        logger.info(f"Created checkout session {session.id} for customer {customer.id}")
        return {"sessionId": session.id}
        
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error creating checkout session: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating checkout session: {str(e)}")
        raise HTTPException(status_code=500, detail="An error occurred while creating the checkout session")

@payment_router.post("/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    
    # Log that we received a webhook
    logger.info("Webhook received")
    logger.info(f"Webhook secret exists: {bool(webhook_secret)}")
    
    if not webhook_secret:
        logger.error("Webhook secret is not configured")
        return JSONResponse(status_code=400, content={"error": "Webhook secret not configured"})
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except ValueError as e:
        # Invalid payload
        logger.error(f"Invalid payload: {str(e)}")
        return JSONResponse(status_code=400, content={"error": str(e)})
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        logger.error(f"Invalid signature: {str(e)}")
        return JSONResponse(status_code=400, content={"error": "Invalid signature"})

    # Log the event type
    logger.info(f"Received event type: {event['type']}")
    
    # Handle the checkout.session.completed event
    if event['type'] == 'checkout.session.completed':
        logger.info("Processing checkout.session.completed event")
        session = event['data']['object']
        await handle_successful_payment(session)
    else:
        logger.info(f"Unhandled event type: {event['type']}")
    
    return JSONResponse(status_code=200, content={"status": "success"})

async def handle_successful_payment(session):
    try:
        # Get the checkout session with expanded line items
        checkout_session = stripe.checkout.Session.retrieve(
            session.id,
            expand=['line_items']
        )
        
        # Get the payment intent
        payment_intent = stripe.PaymentIntent.retrieve(session.payment_intent)
        
        # Get customer email and name
        customer_email = session.customer_email or session.customer_details.email
        customer_name = None
        if session.customer_details:
            customer_name = f"{session.customer_details.get('name', '')}".strip()
        
        # Get product details
        line_item = checkout_session.line_items.data[0]
        product = stripe.Product.retrieve(line_item.price.product)
        
        # Create a record in your database
        payment_data = {
            'stripe_payment_intent_id': session.payment_intent,
            'stripe_customer_id': session.customer,
            'customer_email': customer_email,
            'customer_name': customer_name,
            'amount_total': session.amount_total / 100,  # Convert from cents to dollars
            'currency': session.currency.upper(),
            'payment_status': session.payment_status,
            'product_id': line_item.price.product,
            'product_name': product.name,
            'amount_subtotal': session.amount_subtotal / 100,  # Convert from cents to dollars
            'payment_method': payment_intent.payment_method_types[0] if payment_intent.payment_method_types else None,
            'metadata': dict(session.metadata) if session.metadata else {},
            'created_at': datetime.utcnow().isoformat(),
            'status': 'completed'
        }
        
        # Store payment data in Supabase
        payment_record = {
            'id': str(uuid.uuid4()),
            'created_at': datetime.now(timezone.utc).isoformat(),
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'stripe_payment_intent_id': payment_data['stripe_payment_intent_id'],
            'stripe_customer_id': payment_data['stripe_customer_id'],
            'customer_email': payment_data['customer_email'],
            'customer_name': payment_data['customer_name'],
            'amount_total': payment_data['amount_total'],
            'currency': payment_data['currency'],
            'payment_status': payment_data['payment_status'],
            'product_id': payment_data['product_id'],
            'product_name': payment_data['product_name'],
            'amount_subtotal': payment_data['amount_subtotal'],
            'payment_method': payment_data['payment_method'],
            'metadata': payment_data['metadata'],
            'status': 'completed'
        }
        
        # Insert into Supabase
        supabase = get_supabase_client()
        
        # First, check if payment already exists to avoid duplicates
        existing_payment = await safe_supabase_operation(
            lambda: supabase.table('payments')
                          .select('id')
                          .eq('stripe_payment_intent_id', payment_data['stripe_payment_intent_id'])
                          .execute(),
            "Failed to check for existing payment"
        )
        # Log payment data instead of storing in database
        logger.info("Payment received - data that would be stored in database:")
        logger.info(f"- Payment Intent ID: {payment_data['stripe_payment_intent_id']}")
        logger.info(f"- Customer Email: {payment_data['customer_email']}")
        logger.info(f"- Customer Name: {payment_data['customer_name']}")
        logger.info(f"- Amount: {payment_data['amount_total']} {payment_data['currency']}")
        logger.info(f"- Product: {payment_data['product_name']} (ID: {payment_data['product_id']})")
        logger.info(f"- Payment Method: {payment_data['payment_method']}")
        logger.info(f"- Metadata: {payment_data['metadata']}")
        
        # Log if this was associated with a lead
        if 'lead_id' in payment_data['metadata']:
            logger.info(f"- Associated with lead ID: {payment_data['metadata']['lead_id']}")
            logger.info("  (Would update lead's payment status to 'paid' in production)")
        
        logger.info("Payment processing complete (database storage skipped)")
        
        if not existing_payment.data:
            # Insert new payment record
            await safe_supabase_operation(
                lambda: supabase.table('payments').insert(payment_record).execute(),
                "Failed to insert payment record"
            )
            
            # Also update the leads table if this is associated with a lead
            if 'lead_id' in payment_data['metadata']:
                lead_update = {
                    'payment_status': 'paid',
                    'payment_id': payment_record['id'],
                    'updated_at': datetime.now(timezone.utc).isoformat()
                }
                await safe_supabase_operation(
                    lambda: supabase.table('qualified_leads')
                                  .update(lead_update)
                                  .eq('id', payment_data['metadata']['lead_id'])
                                  .execute(),
                    "Failed to update lead payment status"
                )
        
        # Send invoice email
        await send_invoice_email(
            to_email=customer_email,
            customer_name=customer_name,
            amount=payment_data['amount_total'],
            currency=payment_data['currency'],
            product_name=payment_data['product_name'],
            payment_date=datetime.utcnow().strftime('%B %d, %Y'),
            payment_id=session.payment_intent
        )
        
        logger.info(f"Successfully processed payment: {session.payment_intent}")
        
    except Exception as e:
        logger.error(f"Error handling successful payment: {str(e)}")
        raise

async def send_invoice_email(to_email: str, customer_name: str, amount: float, 
                           currency: str, product_name: str, payment_date: str, 
                           payment_id: str):
    """
    Send an invoice email to the customer
    """
    try:
        # Format amount with currency symbol
        amount_str = f"${amount:.2f}" if currency.lower() == 'usd' else f"{amount:.2f} {currency.upper()}"
        
        # Create email subject and body
        subject = f"Your Invoice for {product_name}"
        
        # Create a simple HTML email
        html_content = f"""
        <html>
            <body>
                <h2>Thank you for your payment!</h2>
                <p>Dear {customer_name or 'Valued Customer'},</p>
                <p>We've received your payment for <strong>{product_name}</strong>.</p>
                
                <h3>Payment Details</h3>
                <table>
                    <tr>
                        <td><strong>Amount Paid:</strong></td>
                        <td>{amount_str}</td>
                    </tr>
                    <tr>
                        <td><strong>Payment Date:</strong></td>
                        <td>{payment_date}</td>
                    </tr>
                    <tr>
                        <td><strong>Payment ID:</strong></td>
                        <td>{payment_id}</td>
                    </tr>
                </table>
                
                <p>This email serves as your receipt. Please keep it for your records.</p>
                
                <p>If you have any questions about your payment, please don't hesitate to contact us.</p>
                
                <p>Best regards,<br>CSA San Francisco Chapter Team</p>
                
                <p style="font-size: 12px; color: #666;">
                    This is an automated message. Please do not reply to this email.
                </p>
            </body>
        </html>
        """.format(
            customer_name=customer_name or 'Valued Customer',
            product_name=product_name,
            amount_str=amount_str,
            payment_date=payment_date,
            payment_id=payment_id
        )
        
        # Import the email service
        from services.email_service import send_mailersend
        
        # Send the invoice email
        await send_mailersend(
            to_email=to_email,
            subject=subject,
            html_body=html_content
        )
        
        logger.info(f"Invoice email sent to {to_email} for payment {payment_id}")
        
    except Exception as e:
        logger.error(f"Error sending invoice email: {str(e)}")
        raise

@payment_router.get("/session/{session_id}")
async def get_session_details(session_id: str):
    """
    Get session details including payment intent ID for a given checkout session.
    """
    try:
        # Retrieve the checkout session
        session = stripe.checkout.Session.retrieve(session_id)
        
        return {
            "payment_intent": session.payment_intent,
            "customer_email": session.customer_details.email if hasattr(session, 'customer_details') and session.customer_details else None,
            "amount_total": session.amount_total / 100 if hasattr(session, 'amount_total') else None,
            "currency": session.currency.upper() if hasattr(session, 'currency') else None
        }
        
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error getting session details: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting session details: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

from fastapi import Query

@payment_router.get("/get-invoice-url")
async def get_invoice_or_receipt(
    payment_intent_id: str = Query(..., description="The payment intent ID to get invoice/receipt for"),
):
    try:
        # First try to get the payment intent with expanded charges
        try:
            payment_intent = stripe.PaymentIntent.retrieve(
                payment_intent_id,
                expand=['latest_charge.invoice']
            )
        except stripe.error.StripeError as e:
            logger.error(f"Error retrieving payment intent: {str(e)}")
            return {
                "type": "error",
                "url": None,
                "message": f"Error retrieving payment details: {str(e)}"
            }

        # Get the latest charge
        if not hasattr(payment_intent, 'latest_charge') or not payment_intent.latest_charge:
            return {
                "type": None,
                "url": None,
                "message": "No charge found for this payment intent"
            }

        # Get the charge object
        charge = payment_intent.latest_charge
        if isinstance(charge, str):
            try:
                charge = stripe.Charge.retrieve(charge, expand=['invoice'])
            except stripe.error.StripeError as e:
                logger.error(f"Error retrieving charge: {str(e)}")
                return {
                    "type": "error",
                    "url": None,
                    "message": f"Error retrieving charge details: {str(e)}"
                }

        # Try to get invoice from charge
        if hasattr(charge, 'invoice') and charge.invoice:
            invoice_id = charge.invoice if isinstance(charge.invoice, str) else charge.invoice.id
            invoice = stripe.Invoice.retrieve(invoice_id)

            print(invoice)
            if invoice.status == 'draft':
                invoice = stripe.Invoice.finalize_invoice(invoice.id)

            print(invoice.invoice_pdf)
            if invoice.invoice_pdf:
                return {
                    "type": "invoice",
                    "url": invoice.invoice_pdf,
                    "invoice_number": invoice.number,
                    "amount_paid": invoice.amount_paid / 100,
                    "currency": invoice.currency.upper(),
                    "status": invoice.status
                }

        # Fallback: receipt
        receipt_url = getattr(charge, "receipt_url", None)

        return {
            "type": "receipt" if receipt_url else None,
            "url": receipt_url,
            "amount_paid": charge.amount / 100,
            "currency": charge.currency.upper(),
            "status": charge.status,
            "message": None if receipt_url else "Receipt URL not yet available"
        }

    except stripe.error.StripeError as e:
        logger.error(f"Stripe error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
