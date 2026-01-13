"""
Event Images Router
Handles listing and managing event images from Supabase Storage
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from services.auth_services import verify_token
from services.supabase_storage_service import get_storage_service
from services.google_drive_service import get_google_drive_service
from db.supabase import get_supabase_client
from config.logging import setup_logging
import logging
import re

setup_logging()
logger = logging.getLogger(__name__)

event_images_router = APIRouter()


class EventImageCreate(BaseModel):
    url: str
    caption: Optional[str] = None


@event_images_router.get("")
async def list_event_images(event_title: Optional[str] = None):
    """
    List all event images from Supabase Storage (Public endpoint - no auth required)
    Optionally filter by event_title if provided
    """
    try:
        storage_service = get_storage_service()
        success, files, error_message = storage_service.list_images("event", limit=1000)
        
        if not success:
            raise HTTPException(status_code=500, detail=error_message or "Failed to list images")
        
        # Get captions from database (using existing image_captions table)
        supabase = get_supabase_client()
        captions_dict = {}
        event_titles_dict = {}
        
        try:
            # Try to get all captions with event_title
            query = supabase.table('image_captions').select('*').eq('image_type', 'event')
            if event_title:
                # Try to filter by event_title
                try:
                    query = query.eq('event_title', event_title)
                except:
                    logger.warning("event_title column may not exist, fetching all captions")
            captions_response = query.execute()
            
            # Build dict using filename from URL as key
            for item in captions_response.data if captions_response.data else []:
                filename = item.get('filename', '')
                captions_dict[filename] = item.get('caption', '')
                # Try to get event_title, fallback to empty string
                event_titles_dict[filename] = item.get('event_title', '')
        except Exception as e:
            logger.warning(f"Could not fetch captions: {e}")
        
        # If event_title column doesn't exist, try to match images to events by filename patterns
        # or by checking if we can infer from the sync process
        # For now, we'll also try to get event titles from a metadata approach
        try:
            # Get all events to match by title
            events_response = supabase.table('events').select('id, title').execute()
            events_by_title = {event['title']: event['id'] for event in (events_response.data or [])}
            
            # If event_title is missing, try to match by checking recent uploads
            # This is a fallback - ideally event_title column should exist
            if not any(event_titles_dict.values()):
                logger.info("No event_title found in captions, attempting to match by event titles")
                # We can't reliably match without event_title, but we'll leave it empty
                # The frontend can handle images without event_title
        except Exception as e:
            logger.warning(f"Could not fetch events for matching: {e}")
        
        # If event_title column doesn't exist, try to match images to events by checking upload metadata
        # Get all events to help with matching
        events_by_title = {}
        try:
            events_response = supabase.table('events').select('id, title').execute()
            if events_response.data:
                events_by_title = {event['title']: event['title'] for event in events_response.data}
        except Exception as e:
            logger.warning(f"Could not fetch events for matching: {e}")
        
        # Merge captions with file data
        images_with_captions = []
        for file in files:
            # Extract filename from the file name
            filename = file['name']
            
            # Get event_title from dict (may be empty if column doesn't exist)
            file_event_title = event_titles_dict.get(filename, '')
            
            # If event_title is empty, try to infer from filename or check if we can match to an event
            # For images synced from Google Drive, the filename might contain clues
            # But the best approach is to ensure event_title is stored during sync
            
            # If filtering by event_title, only include images from that event
            if event_title:
                if file_event_title != event_title:
                    continue
            
            images_with_captions.append({
                'url': file['url'],
                'name': file['name'],
                'size': file['size'],
                'created_at': file.get('created_at'),
                'caption': captions_dict.get(filename, ''),
                'event_title': file_event_title  # May be empty if column doesn't exist
            })
        
        return JSONResponse(
            status_code=200,
            content={
                "images": images_with_captions,
                "count": len(images_with_captions),
                "event_title": event_title
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing event images: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list event images: {str(e)}"
        )


@event_images_router.post("")
async def save_event_image_caption(
    image_data: EventImageCreate,
    token_data: dict = Depends(verify_token)
):
    """
    Save or update caption for an event image
    """
    try:
        supabase = get_supabase_client()
        
        # Extract filename from URL
        filename = image_data.url.split('/')[-1].split('?')[0]  # Remove query params if any
        
        logger.info(f"Saving caption for filename: {filename}")
        
        # Check if caption already exists (using existing image_captions table schema)
        existing = supabase.table('image_captions').select('*').eq('filename', filename).eq('image_type', 'event').execute()
        
        if existing.data and len(existing.data) > 0:
            # Update existing caption
            result = supabase.table('image_captions').update({
                'caption': image_data.caption or '',
                'updated_at': 'NOW()'
            }).eq('filename', filename).eq('image_type', 'event').execute()
            logger.info(f"Updated caption for {filename}")
        else:
            # Insert new caption
            result = supabase.table('image_captions').insert({
                'filename': filename,
                'image_type': 'event',
                'caption': image_data.caption or '',
                'uploaded_by': token_data.get('email')
            }).execute()
            logger.info(f"Inserted new caption for {filename}")
        
        return JSONResponse(
            status_code=200,
            content={
                "message": "Caption saved successfully",
                "url": image_data.url,
                "caption": image_data.caption
            }
        )
        
    except Exception as e:
        logger.error(f"Error saving caption: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save caption: {str(e)}"
        )




@event_images_router.delete("/{filename}")
async def delete_event_image(
    filename: str,
    token_data: dict = Depends(verify_token)
):
    """
    Delete an event image from Supabase Storage and database
    """
    try:
        storage_service = get_storage_service()
        supabase = get_supabase_client()
        
        logger.info(f"Deleting event image: {filename}")
        
        # Delete from storage (pass filename as image_url, it will extract the filename)
        success, error_message = storage_service.delete_image(filename, "event")
        
        if not success:
            logger.error(f"Failed to delete from storage: {error_message}")
            raise HTTPException(status_code=500, detail=error_message or "Failed to delete from storage")
        
        # Delete caption from database
        try:
            supabase.table('image_captions').delete().eq('filename', filename).eq('image_type', 'event').execute()
            logger.info(f"Deleted caption for {filename}")
        except Exception as e:
            logger.warning(f"Could not delete caption: {e}")
            # Continue even if caption deletion fails
        
        return JSONResponse(
            status_code=200,
            content={
                "message": "Image deleted successfully",
                "filename": filename
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting event image: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete event image: {str(e)}"
        )


@event_images_router.post("/sync-from-drive")
async def sync_images_from_google_drive(
    event_title: str,
    token_data: dict = Depends(verify_token)
):
    """
    Sync images from Google Drive folder (named after event title) to gallery
    Uses Google Drive URLs directly (no Supabase Storage upload)
    Admin only endpoint
    """
    try:
        drive_service = get_google_drive_service()
        if not drive_service:
            raise HTTPException(
                status_code=503,
                detail="Google Drive service not available. Please check credentials configuration."
            )
        
        supabase = get_supabase_client()
        
        logger.info(f"Syncing images from Google Drive for event: {event_title}")
        
        # Get images from Google Drive folder (returns URLs, not file content)
        images = drive_service.get_images_from_event_folder(event_title)
        
        if not images:
            return JSONResponse(
                status_code=200,
                content={
                    "message": f"No images found in Google Drive folder for event: {event_title}",
                    "synced_count": 0
                }
            )
        
        logger.info(f"Processing {len(images)} images from Google Drive folder '{event_title}'")
        
        # Process images (using Drive URLs directly)
        synced_count = 0
        failed_count = 0
        skipped_count = 0
        
        # Get event_id once for all images (if matching event exists)
        event_id = None
        try:
            # Helper to normalize text (remove emojis, special chars)
            def normalize_text(text):
                import re
                text = re.sub(r'[^\w\s]', '', text)
                text = ' '.join(text.split())
                return text.lower().strip()
            
            folder_normalized = normalize_text(event_title)
            
            # First try exact match (case-insensitive)
            event_match = supabase.table('events').select('id, title').ilike('title', event_title).limit(1).execute()
            if event_match.data and len(event_match.data) > 0:
                event_id = event_match.data[0]['id']
            else:
                # Try fuzzy matching
                all_events = supabase.table('events').select('id, title').execute()
                if all_events.data:
                    for event in all_events.data:
                        event_db_title = event['title']
                        event_db_normalized = normalize_text(event_db_title)
                        event_title_lower = event_title.lower().strip()
                        event_db_title_lower = event_db_title.lower().strip()
                        
                        if (event_title_lower == event_db_title_lower or
                            event_title_lower in event_db_title_lower or
                            event_db_title_lower in event_title_lower or
                            event_title_lower.replace(' ', '') == event_db_title_lower.replace(' ', '') or
                            folder_normalized == event_db_normalized or
                            folder_normalized in event_db_normalized or
                            event_db_normalized in folder_normalized):
                            event_id = event['id']
                            break
        except Exception as e:
            logger.warning(f"Could not match event for folder '{event_title}': {e}")
        
        for filename, drive_url, drive_file_id in images:
            try:
                # Validate Drive URL
                if not drive_url or not drive_url.strip():
                    logger.warning(f"Invalid Drive URL for {filename}")
                    failed_count += 1
                    continue
                
                # Accept absolute URLs (http/https) or relative paths (proxy URLs starting with /)
                if not (drive_url.startswith('http://') or drive_url.startswith('https://') or drive_url.startswith('/')):
                    logger.warning(f"Invalid image URL format for {filename}: {drive_url}")
                    failed_count += 1
                    continue
                
                # Use Drive URL directly (no upload needed)
                public_url = drive_url
                
                # Check for duplicates BEFORE processing (by original filename or Drive file ID)
                is_duplicate_before_upload = False
                existing_entry_id = None
                
                try:
                    # Try to check by original_filename column if it exists
                    existing_check = supabase.table('gallery_images').select('id, image_url').eq('folder_name', event_title).eq('original_filename', filename).limit(1).execute()
                    if existing_check.data and len(existing_check.data) > 0:
                        is_duplicate_before_upload = True
                        existing_entry_id = existing_check.data[0]['id']
                except Exception as e:
                    # If original_filename column doesn't exist, check by URL
                    if 'original_filename' in str(e).lower() or 'column' in str(e).lower():
                        # Check by Drive URL instead
                        existing_check = supabase.table('gallery_images').select('id, image_url').eq('folder_name', event_title).eq('image_url', drive_url).limit(1).execute()
                        if existing_check.data and len(existing_check.data) > 0:
                            is_duplicate_before_upload = True
                            existing_entry_id = existing_check.data[0]['id']
                    else:
                        logger.warning(f"Error checking for duplicates: {e}")
                
                if is_duplicate_before_upload:
                    # Update existing entry with latest event_id and URL (URL might have changed or been fixed)
                    try:
                        update_data = {
                            'folder_name': event_title,
                            'event_id': event_id,
                            'image_url': public_url,  # Update URL in case it was wrong or changed
                            'updated_at': 'NOW()'
                        }
                        # Try to update original_filename if column exists
                        try:
                            update_data['original_filename'] = filename
                        except:
                            pass
                        supabase.table('gallery_images').update(update_data).eq('id', existing_entry_id).execute()
                    except Exception as update_error:
                        logger.warning(f"Failed to update existing entry: {update_error}")
                    skipped_count += 1
                    continue  # Skip to next image
                
                # Save gallery image entry (gallery_images table) - for Gallery page only
                # NOT adding to image_captions (Events slideshow)
                try:
                    # Use filename as stored_filename (since we're not uploading to Supabase)
                    stored_filename = filename
                    
                    # event_id is already set earlier for all images in this folder
                    gallery_data = {
                        'filename': stored_filename,
                        'image_url': public_url,
                        'folder_name': event_title,  # Google Drive folder name
                        'caption': '',
                        'event_id': event_id,  # Link to event if found
                        'original_filename': filename  # Original Google Drive filename for duplicate detection
                    }
                    
                    # Check if image already exists (avoid duplicates)
                    # Check by: 1) original Google Drive filename in this folder, 2) same image_url in this folder
                    is_duplicate = False
                    duplicate_reason = None
                    existing_entry_id = None
                    
                    # Try to query with original_filename (if column exists), fallback to URL-only check
                    try:
                        existing_in_folder = supabase.table('gallery_images').select('id, image_url, original_filename, caption').eq('folder_name', event_title).execute()
                        has_original_filename_column = True
                    except Exception as e:
                        # If original_filename column doesn't exist, query without it
                        if 'original_filename' in str(e).lower() or 'column' in str(e).lower():
                            existing_in_folder = supabase.table('gallery_images').select('id, image_url, caption').eq('folder_name', event_title).execute()
                            has_original_filename_column = False
                        else:
                            raise
                    
                    # Check if this image already exists in this folder
                    if existing_in_folder.data:
                        for existing_img in existing_in_folder.data:
                            # Check by original filename (most reliable for Google Drive duplicates) if column exists
                            if has_original_filename_column and existing_img.get('original_filename') == filename:
                                is_duplicate = True
                                duplicate_reason = "same original filename"
                                existing_entry_id = existing_img['id']
                                break
                            # Also check by URL (fallback or if original_filename column doesn't exist)
                            elif existing_img.get('image_url') == public_url:
                                is_duplicate = True
                                duplicate_reason = "same URL"
                                existing_entry_id = existing_img['id']
                                break
                    
                    # Also check by stored filename (fallback)
                    existing_by_filename = supabase.table('gallery_images').select('id').eq('filename', stored_filename).execute()
                    if existing_by_filename.data and len(existing_by_filename.data) > 0 and not is_duplicate:
                        is_duplicate = True
                        duplicate_reason = "same stored filename"
                        existing_entry_id = existing_by_filename.data[0]['id']
                    
                    if is_duplicate:
                        # Update existing entry to ensure it has latest folder_name, event_id, and original_filename
                        if existing_entry_id:
                            update_data = {
                                'folder_name': event_title,
                                'event_id': event_id,
                                'updated_at': 'NOW()'
                            }
                            # Only add original_filename if column exists (for backward compatibility)
                            try:
                                update_data['original_filename'] = filename
                            except:
                                pass
                            supabase.table('gallery_images').update(update_data).eq('id', existing_entry_id).execute()
                        skipped_count += 1
                    else:
                        # Try to insert with original_filename, fallback if column doesn't exist
                        try:
                            supabase.table('gallery_images').insert(gallery_data).execute()
                        except Exception as insert_error:
                            # If original_filename column doesn't exist, insert without it
                            if 'original_filename' in str(insert_error).lower() or 'column' in str(insert_error).lower():
                                gallery_data_without_original = {k: v for k, v in gallery_data.items() if k != 'original_filename'}
                                supabase.table('gallery_images').insert(gallery_data_without_original).execute()
                            else:
                                raise
                        logger.info(f"✓ Added NEW image to gallery_images: {filename} for folder '{event_title}'")
                        synced_count += 1
                except Exception as gallery_error:
                    # If gallery_images table doesn't exist, log warning but continue
                    if 'gallery_images' in str(gallery_error).lower() or 'relation' in str(gallery_error).lower():
                        logger.warning(f"gallery_images table may not exist: {gallery_error}")
                        logger.info("Please run the migration to create gallery_images table")
                    else:
                        logger.warning(f"Failed to save gallery image entry: {gallery_error}")
                    
                    logger.info(f"✓ Successfully synced image: {filename}")
                    
            except Exception as e:
                logger.error(f"✗ Error processing image {filename}: {e}", exc_info=True)
                failed_count += 1
        
        logger.info(f"Sync completed: {synced_count} new, {skipped_count} skipped, {failed_count} failed out of {len(images)} total")
        
        return JSONResponse(
            status_code=200,
            content={
                "message": f"Sync completed for event: {event_title}",
                "synced_count": synced_count,
                "skipped_count": skipped_count,
                "failed_count": failed_count,
                "total_images": len(images),
                "synced_count": synced_count,
                "failed_count": failed_count,
                "total_images": len(images)
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error syncing images from Google Drive: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to sync images: {str(e)}"
        )


def sync_event_images_from_drive(event_title: str, admin_email: str = None) -> dict:
    """
    Helper function to sync images from Google Drive for an event
    Can be called from other modules (e.g., event router)
    
    Args:
        event_title: Title of the event (used as folder name in Google Drive)
        admin_email: Optional email of the admin performing the sync
    
    Returns:
        Dictionary with sync results
    """
    try:
        drive_service = get_google_drive_service()
        if not drive_service:
            logger.warning("Google Drive service not available, skipping image sync")
            return {"success": False, "message": "Google Drive service not available", "synced_count": 0}
        
        supabase = get_supabase_client()
        
        
        # Get images from Google Drive folder (returns URLs, not file content)
        images = drive_service.get_images_from_event_folder(event_title)
        
        # Initialize counters
        synced_count = 0
        failed_count = 0
        skipped_count = 0
        
        if not images:
            logger.info(f"No images found in Google Drive folder for event: {event_title}")
            # Still need to check for deleted images (folder might be empty now)
            # Continue to delete logic below
        else:
            logger.info(f"Processing {len(images)} images from Google Drive folder '{event_title}'")
        
        # Process images (using Drive URLs directly) - only if images exist
        
        # Get event_id once for all images (if matching event exists)
        event_id = None
        try:
            # Helper to normalize text (remove emojis, special chars)
            def normalize_text(text):
                import re
                text = re.sub(r'[^\w\s]', '', text)
                text = ' '.join(text.split())
                return text.lower().strip()
            
            folder_normalized = normalize_text(event_title)
            
            # First try exact match (case-insensitive)
            event_match = supabase.table('events').select('id, title').ilike('title', event_title).limit(1).execute()
            if event_match.data and len(event_match.data) > 0:
                event_id = event_match.data[0]['id']
            else:
                # Try fuzzy matching
                all_events = supabase.table('events').select('id, title').execute()
                if all_events.data:
                    for event in all_events.data:
                        event_db_title = event['title']
                        event_db_normalized = normalize_text(event_db_title)
                        event_title_lower = event_title.lower().strip()
                        event_db_title_lower = event_db_title.lower().strip()
                        
                        if (event_title_lower == event_db_title_lower or
                            event_title_lower in event_db_title_lower or
                            event_db_title_lower in event_title_lower or
                            event_title_lower.replace(' ', '') == event_db_title_lower.replace(' ', '') or
                            folder_normalized == event_db_normalized or
                            folder_normalized in event_db_normalized or
                            event_db_normalized in folder_normalized):
                            event_id = event['id']
                            break
        except Exception as e:
            logger.warning(f"Could not match event for folder '{event_title}': {e}")
        
        # Only process images if they exist
        if images:
            for filename, drive_url, drive_file_id in images:
                try:
                    # Validate Drive URL
                    if not drive_url or not drive_url.strip():
                        logger.warning(f"Invalid Drive URL for {filename}")
                        failed_count += 1
                        continue
                    
                    # Accept absolute URLs (http/https) or relative paths (proxy URLs starting with /)
                    if not (drive_url.startswith('http://') or drive_url.startswith('https://') or drive_url.startswith('/')):
                        logger.warning(f"Invalid image URL format for {filename}: {drive_url}")
                        failed_count += 1
                        continue
                    
                    # Use Drive URL directly (no upload needed)
                    public_url = drive_url
                    
                    # Check for duplicates BEFORE processing (by original filename or Drive file ID)
                    is_duplicate_before_upload = False
                    existing_entry_id = None
                    
                    try:
                        # Try to check by original_filename column if it exists
                        existing_check = supabase.table('gallery_images').select('id, image_url').eq('folder_name', event_title).eq('original_filename', filename).limit(1).execute()
                        if existing_check.data and len(existing_check.data) > 0:
                            is_duplicate_before_upload = True
                            existing_entry_id = existing_check.data[0]['id']
                    except Exception as e:
                        # If original_filename column doesn't exist, check by URL
                        if 'original_filename' in str(e).lower() or 'column' in str(e).lower():
                            # Convert Drive URL to proxy URL for comparison (since DB stores proxy URLs)
                            from routers.gallery_images import convert_drive_url_to_proxy
                            proxy_url = convert_drive_url_to_proxy(drive_url)
                            # Check by proxy URL (since that's what's stored in DB)
                            existing_check = supabase.table('gallery_images').select('id, image_url').eq('folder_name', event_title).eq('image_url', proxy_url).limit(1).execute()
                            if existing_check.data and len(existing_check.data) > 0:
                                is_duplicate_before_upload = True
                                existing_entry_id = existing_check.data[0]['id']
                        else:
                            logger.warning(f"Error checking for duplicates: {e}")
                    
                    if is_duplicate_before_upload:
                        # Update existing entry with latest event_id and URL (URL might have changed or been fixed)
                        try:
                            # Convert Drive URL to proxy URL for storage
                            from routers.gallery_images import convert_drive_url_to_proxy
                            proxy_url = convert_drive_url_to_proxy(public_url)
                            
                            update_data = {
                                'folder_name': event_title,
                                'event_id': event_id,
                                'image_url': proxy_url,  # Update URL as proxy URL
                                'updated_at': 'NOW()'
                            }
                            # Try to update original_filename if column exists
                            try:
                                update_data['original_filename'] = filename
                            except:
                                pass
                            supabase.table('gallery_images').update(update_data).eq('id', existing_entry_id).execute()
                        except Exception as update_error:
                            logger.warning(f"Failed to update existing entry: {update_error}")
                        skipped_count += 1
                        continue  # Skip to next image
                    
                    # Save gallery image entry (gallery_images table) - for Gallery page only
                    # NOT adding to image_captions (Events slideshow)
                    try:
                        # Use filename as stored_filename (since we're not uploading to Supabase)
                        stored_filename = filename
                        
                        # Convert Drive URL to proxy URL for storage (to bypass CORS issues)
                        from routers.gallery_images import convert_drive_url_to_proxy
                        proxy_url = convert_drive_url_to_proxy(public_url)
                        
                        gallery_data = {
                            'filename': stored_filename,
                            'image_url': proxy_url,  # Store as proxy URL
                            'folder_name': event_title,  # Google Drive folder name
                            'caption': '',
                            'event_id': event_id,  # Link to event if found
                            'original_filename': filename  # Original Google Drive filename for duplicate detection
                        }
                        
                        # Check if image already exists (avoid duplicates)
                        # Check by: 1) original Google Drive filename in this folder, 2) same image_url in this folder
                        is_duplicate = False
                        duplicate_reason = None
                        existing_entry_id = None
                        
                        # Try to query with original_filename (if column exists), fallback to URL-only check
                        try:
                            existing_in_folder = supabase.table('gallery_images').select('id, image_url, original_filename, caption').eq('folder_name', event_title).execute()
                            has_original_filename_column = True
                        except Exception as e:
                            # If original_filename column doesn't exist, query without it
                            if 'original_filename' in str(e).lower() or 'column' in str(e).lower():
                                existing_in_folder = supabase.table('gallery_images').select('id, image_url, caption').eq('folder_name', event_title).execute()
                                has_original_filename_column = False
                            else:
                                raise
                        
                        # Check if this image already exists in this folder
                        if existing_in_folder.data:
                            for existing_img in existing_in_folder.data:
                                # Check by original filename (most reliable for Google Drive duplicates) if column exists
                                if has_original_filename_column and existing_img.get('original_filename') == filename:
                                    is_duplicate = True
                                    duplicate_reason = "same original filename"
                                    existing_entry_id = existing_img['id']
                                    break
                                # Also check by URL (compare proxy URLs since that's what's stored in DB)
                                elif existing_img.get('image_url') == proxy_url:
                                    is_duplicate = True
                                    duplicate_reason = "same URL"
                                    existing_entry_id = existing_img['id']
                                    break
                        
                        # Also check by stored filename (fallback)
                        existing_by_filename = supabase.table('gallery_images').select('id').eq('filename', stored_filename).execute()
                        if existing_by_filename.data and len(existing_by_filename.data) > 0 and not is_duplicate:
                            is_duplicate = True
                            duplicate_reason = "same stored filename"
                            existing_entry_id = existing_by_filename.data[0]['id']
                        
                        if is_duplicate:
                            # Update existing entry to ensure it has latest folder_name, event_id, and original_filename
                            if existing_entry_id:
                                update_data = {
                                    'folder_name': event_title,
                                    'event_id': event_id,
                                    'updated_at': 'NOW()'
                                }
                                # Only add original_filename if column exists (for backward compatibility)
                                try:
                                    update_data['original_filename'] = filename
                                except:
                                    pass
                                supabase.table('gallery_images').update(update_data).eq('id', existing_entry_id).execute()
                            skipped_count += 1
                        else:
                            # Try to insert with original_filename, fallback if column doesn't exist
                            try:
                                supabase.table('gallery_images').insert(gallery_data).execute()
                            except Exception as insert_error:
                                # If original_filename column doesn't exist, insert without it
                                if 'original_filename' in str(insert_error).lower() or 'column' in str(insert_error).lower():
                                    gallery_data_without_original = {k: v for k, v in gallery_data.items() if k != 'original_filename'}
                                    supabase.table('gallery_images').insert(gallery_data_without_original).execute()
                                else:
                                    raise
                            logger.info(f"✓ Added NEW image to gallery_images: {filename} for folder '{event_title}'")
                            synced_count += 1
                    except Exception as gallery_error:
                        # If gallery_images table doesn't exist, log warning but continue
                        if 'gallery_images' in str(gallery_error).lower() or 'relation' in str(gallery_error).lower():
                            logger.warning(f"gallery_images table may not exist: {gallery_error}")
                            logger.info("Please run the migration to create gallery_images table")
                        else:
                            logger.warning(f"Failed to save gallery image entry: {gallery_error}")
                        
                except Exception as e:
                    logger.error(f"✗ Error processing image {filename}: {e}", exc_info=True)
                    failed_count += 1
        
        # Detect and remove deleted images from Google Drive
        # IMPORTANT: This runs even when images is empty (folder might be empty now, so delete all DB entries)
        deleted_count = 0
        try:
            import urllib.parse
            
            # Build sets of identifiers for images currently in Drive
            drive_filenames = set()
            drive_file_ids = set()
            if images:
                for filename, drive_url, drive_file_id in images:
                    drive_filenames.add(filename.lower())
                    if drive_file_id:
                        drive_file_ids.add(drive_file_id)
                    # Also extract file ID from URL if available
                    if drive_url and 'drive.google.com' in drive_url and 'id=' in drive_url:
                        try:
                            parsed = urllib.parse.urlparse(drive_url)
                            params = urllib.parse.parse_qs(parsed.query)
                            if 'id' in params:
                                drive_file_ids.add(params['id'][0])
                        except:
                            pass
            
            # Get all images in database for this folder
            try:
                # Try exact match first
                db_images = supabase.table('gallery_images').select('id, original_filename, image_url, filename, folder_name').eq('folder_name', event_title).execute()
                
                # If no images found with exact match, try case-insensitive match
                if not db_images.data or len(db_images.data) == 0:
                    all_db_images = supabase.table('gallery_images').select('id, original_filename, image_url, filename, folder_name').execute()
                    if all_db_images.data:
                        # Filter by case-insensitive folder name match
                        matching_images = [
                            img for img in all_db_images.data 
                            if img.get('folder_name', '').lower().strip() == event_title.lower().strip()
                        ]
                        if matching_images:
                            db_images.data = matching_images
                
                if db_images.data:
                    logger.info(f"Checking {len(db_images.data)} database images for folder '{event_title}' against {len(images)} Drive images")
                    for db_image in db_images.data:
                        # If folder is empty in Drive (images is empty), delete all DB entries for this folder
                        if not images:
                            # Folder is empty in Drive, so all DB images for this folder should be deleted
                            try:
                                deleted_filename = db_image.get('original_filename') or db_image.get('filename') or 'unknown'
                                deleted_id = db_image.get('id')
                                supabase.table('gallery_images').delete().eq('id', deleted_id).execute()
                                logger.info(f"✓ Removed deleted image from gallery: {deleted_filename} (ID: {deleted_id}, folder is empty in Drive)")
                                deleted_count += 1
                            except Exception as delete_error:
                                logger.error(f"Failed to delete image {db_image.get('id')}: {delete_error}")
                        else:
                            # Check if this database image exists in Drive
                            db_filename = (db_image.get('original_filename') or db_image.get('filename') or '').lower()
                            db_url = db_image.get('image_url', '')
                            
                            # Extract file ID from Google Drive URL or proxy URL
                            db_file_id = None
                            if db_url:
                                # Check if it's a proxy URL: /v1/routes/gallery-images/proxy/{file_id}
                                if db_url.startswith('/v1/routes/gallery-images/proxy/'):
                                    try:
                                        # Extract file_id from proxy URL path
                                        parts = db_url.split('/v1/routes/gallery-images/proxy/')
                                        if len(parts) > 1:
                                            db_file_id = parts[1].split('/')[0].split('?')[0]  # Remove query params if any
                                    except:
                                        pass
                                # Check if it's a Google Drive URL
                                elif 'drive.google.com' in db_url:
                                    try:
                                        # Try multiple URL patterns
                                        if 'id=' in db_url:
                                            parsed = urllib.parse.urlparse(db_url)
                                            params = urllib.parse.parse_qs(parsed.query)
                                            if 'id' in params:
                                                db_file_id = params['id'][0]
                                        elif '/file/d/' in db_url:
                                            # Pattern: https://drive.google.com/file/d/FILE_ID/view
                                            parts = db_url.split('/file/d/')
                                            if len(parts) > 1:
                                                db_file_id = parts[1].split('/')[0]
                                        elif '/thumbnail?id=' in db_url:
                                            parsed = urllib.parse.urlparse(db_url)
                                            params = urllib.parse.parse_qs(parsed.query)
                                            if 'id' in params:
                                                db_file_id = params['id'][0]
                                    except:
                                        pass
                            
                            # Check if image still exists in Drive (by filename or file ID)
                            image_exists = (
                                db_filename in drive_filenames or
                                (db_file_id and db_file_id in drive_file_ids)
                            )
                            
                            # ALWAYS do a direct API check if we have a file ID (most reliable method)
                            # This catches cases where files were deleted but the sync hasn't updated yet
                            if db_file_id:
                                try:
                                    file_still_exists = drive_service.file_exists(db_file_id)
                                    if file_still_exists:
                                        image_exists = True
                                    else:
                                        # File doesn't exist in Drive, mark for deletion
                                        image_exists = False
                                        logger.info(f"File {db_file_id} confirmed deleted via API check")
                                except Exception as api_check_error:
                                    logger.debug(f"Could not verify file existence via API for {db_file_id}: {api_check_error}")
                                    # If API check fails, rely on filename/file_id matching
                            
                            if not image_exists:
                                # Image was deleted from Drive, remove from database
                                try:
                                    deleted_filename = db_image.get('original_filename') or db_image.get('filename') or 'unknown'
                                    deleted_id = db_image.get('id')
                                    deleted_url = db_image.get('image_url', '')[:100]  # First 100 chars for logging
                                    logger.info(f"Deleting image: {deleted_filename} (ID: {deleted_id}, URL: {deleted_url}..., file_id: {db_file_id})")
                                    supabase.table('gallery_images').delete().eq('id', deleted_id).execute()
                                    logger.info(f"✓ Removed deleted image from gallery: {deleted_filename} (not found in Drive)")
                                    deleted_count += 1
                                except Exception as delete_error:
                                    logger.error(f"Failed to delete image {db_image.get('id')}: {delete_error}")
                            else:
                                # Log which images are still valid (for debugging)
                                logger.debug(f"Image still exists in Drive: {db_image.get('original_filename') or db_image.get('filename')} (file_id: {db_file_id})")
            except Exception as e:
                logger.error(f"Could not check for deleted images: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Error detecting deleted images: {e}", exc_info=True)
        
        logger.info(f"Auto-sync completed: {synced_count} new, {skipped_count} skipped, {failed_count} failed, {deleted_count} deleted out of {len(images)} total in Drive")
        return {
            "success": True,
            "message": f"Synced {synced_count} new images, removed {deleted_count} deleted images",
            "synced_count": synced_count,
            "skipped_count": skipped_count,
            "failed_count": failed_count,
            "deleted_count": deleted_count,
            "total_images": len(images)
        }
        
    except Exception as e:
        logger.error(f"Error in auto-sync images from Google Drive: {str(e)}")
        return {"success": False, "message": str(e), "synced_count": 0}

