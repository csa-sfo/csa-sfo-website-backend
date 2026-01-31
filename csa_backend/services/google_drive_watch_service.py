"""
Google Drive Watch Service
Sets up push notifications from Google Drive using the Changes API watch() method
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict
from googleapiclient.errors import HttpError
from services.google_drive_service import get_google_drive_service
from config.settings import GOOGLE_DRIVE_WEBHOOK_URL, GOOGLE_DRIVE_FOLDER_ID
import uuid

logger = logging.getLogger(__name__)

# Store active watch channels
_active_channels: Dict[str, Dict] = {}


async def setup_google_drive_watch():
    """
    Set up Google Drive push notifications (watch) for real-time updates
    This replaces polling with instant notifications
    """
    try:
        if not GOOGLE_DRIVE_WEBHOOK_URL:
            logger.warning("GOOGLE_DRIVE_WEBHOOK_URL not configured, cannot set up push notifications")
            return False
        
        drive_service = get_google_drive_service()
        if not drive_service or not drive_service.service:
            logger.warning("Google Drive service not available, cannot set up watch")
            return False
        
        logger.info(f"Setting up Google Drive push notifications (webhook: {GOOGLE_DRIVE_WEBHOOK_URL})")
        
        # Generate a unique channel ID
        channel_id = str(uuid.uuid4())
        
        # Set up watch on the Changes API
        # This watches for changes to all files the service account has access to
        watch_request = {
            'id': channel_id,
            'type': 'web_hook',
            'address': GOOGLE_DRIVE_WEBHOOK_URL,
            'expiration': int((datetime.now() + timedelta(days=7)).timestamp() * 1000)  # 7 days from now
        }
        
        try:
            # Get the start page token first (required for watch)
            start_page_token = drive_service.service.changes().getStartPageToken().execute()
            page_token = start_page_token.get('startPageToken')
            
            if not page_token:
                logger.error("Failed to get start page token from Google Drive")
                return False
            
            logger.info(f"Starting watch from page token: {page_token}")
            
            # Start watching for changes
            # If GOOGLE_DRIVE_FOLDER_ID is set, we could watch a specific folder
            # But watching all changes is simpler and more reliable
            result = drive_service.service.changes().watch(
                pageToken=page_token,  # Use the actual start page token
                body=watch_request
            ).execute()
            
            resource_id = result.get('resourceId')
            expiration = result.get('expiration')
            
            if resource_id:
                _active_channels[channel_id] = {
                    'resource_id': resource_id,
                    'expiration': expiration,
                    'created_at': datetime.now()
                }
                
                logger.info(f"✓ Google Drive watch subscription created successfully")
                logger.info(f"  Channel ID: {channel_id}")
                logger.info(f"  Resource ID: {resource_id}")
                logger.info(f"  Expires at: {datetime.fromtimestamp(int(expiration) / 1000)}")
                logger.info("  Real-time notifications are now active!")
                
                # Start background task to renew watch before expiration
                asyncio.create_task(_renew_watch_before_expiration(channel_id, expiration))
                
                return True
            else:
                logger.error("Failed to get resource ID from watch response")
                return False
                
        except HttpError as e:
            logger.error(f"Error setting up Google Drive watch: {e}")
            if e.resp.status == 403:
                logger.error("Permission denied. Make sure the service account has 'drive.readonly' scope")
            return False
        except Exception as e:
            logger.error(f"Unexpected error setting up watch: {e}")
            return False
            
    except Exception as e:
        logger.error(f"Error in setup_google_drive_watch: {e}")
        return False


async def _renew_watch_before_expiration(channel_id: str, expiration_timestamp: str):
    """
    Renew the watch subscription before it expires
    Google Drive watch subscriptions expire after 7 days
    """
    try:
        expiration_time = datetime.fromtimestamp(int(expiration_timestamp) / 1000)
        # Renew 1 day before expiration
        renewal_time = expiration_time - timedelta(days=1)
        wait_seconds = (renewal_time - datetime.now()).total_seconds()
        
        if wait_seconds > 0:
            logger.info(f"Watch subscription will be renewed in {wait_seconds / 3600:.1f} hours")
            await asyncio.sleep(wait_seconds)
        
        # Renew the watch
        logger.info("Renewing Google Drive watch subscription...")
        await setup_google_drive_watch()
        
        # Stop the old channel if it exists
        await stop_watch_channel(channel_id)
        
    except Exception as e:
        logger.error(f"Error renewing watch: {e}")


async def stop_watch_channel(channel_id: str):
    """
    Stop a watch channel by ID
    """
    try:
        drive_service = get_google_drive_service()
        if not drive_service or not drive_service.service:
            return
        
        channel_info = _active_channels.get(channel_id)
        if not channel_info:
            logger.warning(f"Channel {channel_id} not found in active channels")
            return
        
        resource_id = channel_info.get('resource_id')
        
        # Stop the channel
        drive_service.service.channels().stop(
            body={
                'id': channel_id,
                'resourceId': resource_id
            }
        ).execute()
        
        # Remove from active channels
        del _active_channels[channel_id]
        logger.info(f"Stopped watch channel: {channel_id}")
        
    except Exception as e:
        logger.error(f"Error stopping watch channel: {e}")


async def stop_all_watch_channels():
    """
    Stop all active watch channels (cleanup on shutdown)
    """
    channel_ids = list(_active_channels.keys())
    for channel_id in channel_ids:
        await stop_watch_channel(channel_id)

