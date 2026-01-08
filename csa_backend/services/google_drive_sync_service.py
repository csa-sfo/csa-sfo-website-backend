"""
Google Drive Auto-Sync Service
Monitors Google Drive folders and automatically syncs new images to Gallery
"""

import logging
import asyncio
from typing import Dict, Set, Optional
from datetime import datetime
from services.google_drive_service import get_google_drive_service
from db.supabase import get_supabase_client
from routers.event_images import sync_event_images_from_drive

logger = logging.getLogger(__name__)

# Track last sync time for each folder
_folder_last_sync: Dict[str, datetime] = {}
_folder_last_image_count: Dict[str, int] = {}

# Lock to prevent concurrent syncs (prevents memory corruption and SSL errors)
_sync_lock = asyncio.Lock()
_sync_in_progress = False


async def sync_all_drive_folders():
    """
    Check all folders in Google Drive (or specified root folder) and sync new images
    This function is called periodically by the background task
    
    Uses a lock to prevent concurrent syncs (which can cause memory corruption and SSL errors)
    """
    global _sync_in_progress
    
    # Prevent concurrent syncs - if one is already running, skip this one
    if _sync_in_progress:
        logger.debug("Sync already in progress, skipping concurrent sync request")
        return
    
    async with _sync_lock:
        if _sync_in_progress:
            logger.debug("Sync already in progress (double-check), skipping")
            return
        
        _sync_in_progress = True
        try:
            drive_service = get_google_drive_service()
            if not drive_service or not drive_service.service:
                logger.warning("Google Drive service not available, skipping sync")
                return
            
            # Get all folders in the root folder (or all folders if no root specified)
            # Run in executor since it's a synchronous operation
            loop = asyncio.get_event_loop()
            
            # Add retry logic for SSL errors
            max_retries = 3
            folders = {}
            for attempt in range(max_retries):
                try:
                    folders = await loop.run_in_executor(None, _get_all_folders, drive_service)
                    break
                except Exception as e:
                    if 'SSL' in str(e) or 'wrong version' in str(e).lower():
                        if attempt < max_retries - 1:
                            wait_time = (attempt + 1) * 2  # 2, 4, 6 seconds
                            logger.warning(f"SSL error getting folders (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s...")
                            await asyncio.sleep(wait_time)
                            continue
                    logger.error(f"Error getting folders from Google Drive: {e}")
                    return
            
            if not folders:
                logger.info("No folders found in Google Drive to sync")
                return
            
            
            for folder_name, folder_id in folders.items():
                try:
                    await _sync_folder_if_updated(drive_service, folder_name, folder_id)
                except Exception as e:
                    logger.error(f"Error syncing folder '{folder_name}': {e}")
                    continue
        
        except Exception as e:
            logger.error(f"Error in sync_all_drive_folders: {e}", exc_info=True)
        finally:
            _sync_in_progress = False


def _get_all_folders(drive_service) -> Dict[str, str]:
    """
    Get all folders from Google Drive
    Returns dict mapping folder_name -> folder_id
    
    Includes retry logic for transient SSL errors
    """
    folders = {}
    
    try:
        if not drive_service.service:
            return {}
        
        # Build query for folders
        query = "mimeType='application/vnd.google-apps.folder' and trashed=false"
        
        # If root folder is specified, search within it
        if drive_service.root_folder_id:
            query += f" and '{drive_service.root_folder_id}' in parents"
        
        # List all folders with retry for SSL errors
        max_retries = 3
        results = None
        for attempt in range(max_retries):
            try:
                results = drive_service.service.files().list(
                    q=query,
                    fields="files(id, name, modifiedTime)",
                    pageSize=1000
                ).execute()
                break
            except Exception as e:
                error_str = str(e).lower()
                if ('ssl' in error_str or 'wrong version' in error_str or 'connection' in error_str) and attempt < max_retries - 1:
                    import time
                    wait_time = (attempt + 1) * 1  # 1, 2, 3 seconds
                    logger.warning(f"Transient SSL/connection error (attempt {attempt + 1}/{max_retries}), retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                raise
        
        if not results:
            logger.warning("No results returned from Google Drive API")
            return {}
        
        files = results.get('files', [])
        
        for file in files:
            folders[file['name']] = file['id']
        
        return folders
        
    except Exception as e:
        logger.error(f"Error getting folders from Google Drive: {e}")
        return {}


async def _sync_folder_if_updated(
    drive_service,
    folder_name: str,
    folder_id: str
):
    """
    Check if a folder has new images and sync them if needed
    """
    try:
        # List images in the folder (run in executor since it's synchronous)
        loop = asyncio.get_event_loop()
        images = await loop.run_in_executor(None, drive_service.list_images_in_folder, folder_id)
        
        if not images:
            # No images in folder, skip
            return
        
        current_image_count = len(images)
        last_sync_time = _folder_last_sync.get(folder_name)
        last_image_count = _folder_last_image_count.get(folder_name, 0)
        
        # Always sync to ensure all images are checked (duplicate detection will handle skipping)
        # This ensures we catch cases where images were added but not synced due to errors
        
        # Sync images for this folder (using folder name as event title)
        # Run in executor since sync_event_images_from_drive is synchronous
        loop = asyncio.get_event_loop()
        sync_result = await loop.run_in_executor(None, sync_event_images_from_drive, folder_name, 'system')
        
        if sync_result.get('success'):
            synced_count = sync_result.get('synced_count', 0)
            skipped_count = sync_result.get('skipped_count', 0)
            failed_count = sync_result.get('failed_count', 0)
            
            # Update tracking
            _folder_last_sync[folder_name] = datetime.now()
            _folder_last_image_count[folder_name] = current_image_count
        else:
            logger.warning(f"Failed to sync images from folder '{folder_name}': {sync_result.get('message')}")
            
    except Exception as e:
        logger.error(f"Error checking folder '{folder_name}': {e}")


async def start_google_drive_sync_task(interval_minutes: int = 2, enabled: bool = True):
    """
    Start the background task to periodically sync Google Drive folders
    This is a fallback if webhooks are not available or fail
    
    Args:
        interval_minutes: How often to check for new images (default: 2 minutes)
        enabled: Whether polling is enabled (set to False when webhooks are active)
    """
    from config.settings import GOOGLE_DRIVE_WEBHOOK_URL
    
    if not enabled:
        logger.info("Google Drive polling disabled - using push notifications (webhooks) only")
        return
    
    # If webhook URL is configured, use longer interval (webhooks handle real-time)
    # Otherwise, use shorter interval for near real-time polling
    if GOOGLE_DRIVE_WEBHOOK_URL:
        logger.info(f"Google Drive webhook configured at {GOOGLE_DRIVE_WEBHOOK_URL}")
        logger.info(f"Starting fallback polling task (checking every {interval_minutes} minutes as backup)")
        sync_label = "polling fallback"
    else:
        logger.info(f"Google Drive polling enabled - checking every {interval_minutes} minutes")
        logger.info("  Polling will automatically sync images from Google Drive folders")
        logger.info("  To use webhooks for real-time sync, set CSA_GOOGLE_DRIVE_WEBHOOK_URL environment variable")
        sync_label = "polling"
    
    while True:
        try:
            await asyncio.sleep(interval_minutes * 60)  # Convert minutes to seconds
            await sync_all_drive_folders()
        except Exception as e:
            logger.error(f"Error in Google Drive sync task: {e}")
            # Continue running even if there's an error
            await asyncio.sleep(60)  # Wait 1 minute before retrying

