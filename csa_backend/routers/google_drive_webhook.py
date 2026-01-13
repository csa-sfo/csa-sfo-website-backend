"""
Google Drive Webhook Router
Handles real-time notifications from Google Drive when files are added/changed
"""

from fastapi import APIRouter, Request, HTTPException, Header, BackgroundTasks
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from typing import Optional, Dict
import logging
import json
from datetime import datetime
from services.google_drive_service import get_google_drive_service
from routers.event_images import sync_event_images_from_drive
from db.supabase import get_supabase_client
import asyncio

logger = logging.getLogger(__name__)

google_drive_webhook_router = APIRouter()

# Debounce webhook notifications to prevent too many simultaneous syncs
_last_notification_time = None
_notification_debounce_seconds = 10  # Wait 10 seconds between syncs to avoid excessive API calls (deletions bypass this)


class GoogleDriveNotification(BaseModel):
    """Google Drive push notification payload"""
    kind: Optional[str] = None
    id: Optional[str] = None
    resourceId: Optional[str] = None
    resourceState: Optional[str] = None
    resourceUri: Optional[str] = None
    channelId: Optional[str] = None
    expiration: Optional[str] = None
    changed: Optional[str] = None


@google_drive_webhook_router.get("/webhook")
async def google_drive_webhook_get(request: Request):
    """
    Handle Google Drive webhook verification (GET request)
    Google Drive sends a GET request to verify the webhook endpoint
    """
    # Google Drive sends verification token in query params
    token = request.query_params.get("token")
    challenge = request.query_params.get("challenge")
    
    if challenge:
        logger.info("Google Drive webhook verification received")
        # Return the challenge to verify the webhook
        return Response(content=challenge, media_type="text/plain")
    
    return JSONResponse(status_code=200, content={"status": "ok"})


@google_drive_webhook_router.post("/webhook")
async def google_drive_webhook_post(request: Request, background_tasks: BackgroundTasks):
    """
    Handle Google Drive push notifications (POST request)
    Called when files are added/changed in Google Drive
    
    IMPORTANT: Returns immediately to avoid timeout (502 errors).
    Processing happens in background task.
    """
    try:
        # Get the notification payload
        body = await request.body()
        headers = dict(request.headers)
        
        # Parse the notification
        try:
            notification_data = json.loads(body.decode()) if body else {}
        except:
            notification_data = {}
        
        logger.info("Google Drive webhook notification received")
        
        # Google Drive sends notifications with resourceState field
        # "sync" = initial sync, "update" = file changed, "trash" = file deleted
        resource_state = notification_data.get("resourceState")
        
        # Also check X-Goog-Resource-State header (Google Drive may send it in headers)
        if not resource_state:
            resource_state = headers.get("X-Goog-Resource-State") or headers.get("x-goog-resource-state")
        
        # IMPORTANT: Process in background to avoid timeout
        # Google Drive expects a response within ~10 seconds
        # Sync can take longer, so we return immediately and process async
        logger.info(f"Queueing notification for background processing (resourceState: {resource_state or 'unknown'})")
        
        # Schedule background task - this runs after the response is sent
        background_tasks.add_task(process_drive_change_notification, notification_data)
        
        # Return immediately to prevent timeout (502 Bad Gateway)
        return JSONResponse(
            status_code=200, 
            content={"status": "accepted", "message": "Notification queued for processing"}
        )
        
    except Exception as e:
        logger.error(f"Error processing Google Drive webhook: {e}", exc_info=True)
        # Still return 200 to prevent Google from retrying
        return JSONResponse(status_code=200, content={"status": "error", "message": str(e)})


async def process_drive_change_notification(notification_data: Dict):
    """
    Process a Google Drive change notification and sync affected folders
    
    Includes debouncing to prevent too many simultaneous syncs, but processes deletions immediately
    """
    global _last_notification_time
    
    try:
        resource_state = notification_data.get("resourceState")
        is_deletion = resource_state == "trash"
        
        # For deletions, process immediately without debouncing to ensure quick removal
        # For other changes, use debouncing to prevent too many syncs
        now = datetime.now()
        if not is_deletion and _last_notification_time:
            time_since_last = (now - _last_notification_time).total_seconds()
            if time_since_last < _notification_debounce_seconds:
                logger.debug(f"Skipping notification (debounced, last sync was {time_since_last:.1f}s ago)")
                return
        
        _last_notification_time = now
        
        drive_service = get_google_drive_service()
        if not drive_service or not drive_service.service:
            logger.error(
                "Google Drive service not available, skipping notification processing. "
                "This usually means authentication failed. Check logs for authentication errors. "
                "Images will not be synced until authentication is fixed."
            )
            return
        
        if is_deletion:
            logger.info("Processing Google Drive DELETE notification - syncing all folders immediately")
        else:
            logger.info("Processing Google Drive change notification - syncing all folders")
        
        # Simplified approach: When we receive a notification, sync all folders
        # This is more reliable than trying to parse specific changes
        # The sync function has duplicate detection and locking, so it's safe to sync everything
        await sync_all_folders_on_notification()
            
    except Exception as e:
        logger.error(f"Error processing drive change notification: {e}", exc_info=True)


async def sync_all_folders_on_notification():
    """
    Fallback: sync all folders when we can't determine which specific folder changed
    """
    try:
        from services.google_drive_sync_service import sync_all_drive_folders
        await sync_all_drive_folders()
    except Exception as e:
        logger.error(f"Error in fallback folder sync: {e}")

