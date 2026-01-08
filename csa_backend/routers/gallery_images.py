"""
Gallery Images Router
Handles gallery images from Google Drive, matching them to events by folder name
Separate from image_captions which is used for Events slideshow
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response
from typing import Optional, Dict, List
from db.supabase import get_supabase_client
from services.google_drive_service import get_google_drive_service
from config.logging import setup_logging
import logging
import re

setup_logging()
logger = logging.getLogger(__name__)

gallery_images_router = APIRouter()


def convert_drive_url_to_proxy(image_url: str) -> str:
    """
    Convert Google Drive URL to proxy URL to bypass CORS issues
    
    Args:
        image_url: Original Google Drive URL or proxy URL
    
    Returns:
        Proxy URL path (relative) if it's a Drive URL, otherwise returns original URL
    """
    if not image_url or not isinstance(image_url, str):
        return image_url
    
    # If already a proxy URL, return as-is
    if image_url.startswith('/v1/routes/gallery-images/proxy/'):
        return image_url
    
    # Extract file ID from various Google Drive URL formats
    import re
    
    # Pattern 1: https://drive.google.com/uc?id=FILE_ID&export=view
    # Pattern 2: https://drive.google.com/file/d/FILE_ID/view
    # Pattern 3: https://drive.google.com/thumbnail?id=FILE_ID&sz=w1920
    # Pattern 4: https://drive.google.com/uc?export=view&id=FILE_ID
    
    patterns = [
        r'[?&]id=([a-zA-Z0-9_-]+)',  # id=FILE_ID
        r'/file/d/([a-zA-Z0-9_-]+)',  # /file/d/FILE_ID
        r'/thumbnail\?id=([a-zA-Z0-9_-]+)',  # /thumbnail?id=FILE_ID
    ]
    
    for pattern in patterns:
        match = re.search(pattern, image_url)
        if match:
            file_id = match.group(1)
            return f"/v1/routes/gallery-images/proxy/{file_id}"
    
    # If no file ID found, return original URL (might be a different type of URL)
    return image_url


@gallery_images_router.get("")
async def get_gallery_images():
    """
    Get gallery images grouped by event (folder name from Google Drive)
    Uses gallery_images table to track which folder each image came from
    Matches folder names to event titles and returns gallery-ready data
    Public endpoint - no auth required
    """
    try:
        supabase = get_supabase_client()
        
        # Get all events to match by title - include all event details
        events_response = supabase.table('events').select('id, title, date_time, location, tags, excerpt, description').execute()
        events_by_title = {}
        events_by_id = {}
        if events_response.data:
            for event in events_response.data:
                title_lower = event['title'].lower().strip()
                events_by_title[title_lower] = event
                events_by_id[event['id']] = event
        
        # Get all gallery images grouped by folder_name
        try:
            gallery_response = supabase.table('gallery_images').select('*').order('created_at', desc=False).execute()
            gallery_images = gallery_response.data if gallery_response.data else []
        except Exception as e:
            # If table doesn't exist, return empty
            logger.error(f"gallery_images table may not exist: {e}")
            return JSONResponse(
                status_code=200,
                content={
                    "events": [],
                    "message": "gallery_images table not found. Please run the migration.",
                    "error": str(e)
                }
            )
        
        # Group images by folder_name
        images_by_folder: Dict[str, List[dict]] = {}
        for img in gallery_images:
            folder_name = img.get('folder_name', '').strip()
            image_url = img.get('image_url', '').strip()
            
            
            if folder_name:
                if folder_name not in images_by_folder:
                    images_by_folder[folder_name] = []
                
                # Convert Google Drive URLs to proxy URLs to bypass CORS
                proxy_url = convert_drive_url_to_proxy(image_url)
                
                images_by_folder[folder_name].append({
                    'url': proxy_url,
                    'name': img.get('filename', ''),
                    'caption': img.get('caption', ''),
                    'created_at': img.get('created_at')
                })
        
        
        # Create gallery events from grouped images
        gallery_events = []
        for folder_name, images in images_by_folder.items():
            # Try to find matching event - try multiple matching strategies
            folder_name_lower = folder_name.lower().strip()
            matching_event = events_by_title.get(folder_name_lower)
            
            # Helper function to normalize text (remove emojis, special chars, extra spaces)
            def normalize_text(text):
                import re
                # Remove emojis and special characters, keep only alphanumeric and spaces
                text = re.sub(r'[^\w\s]', '', text)
                # Normalize whitespace
                text = ' '.join(text.split())
                return text.lower().strip()
            
            # If exact match not found, try fuzzy matching (contains, starts with, etc.)
            if not matching_event:
                folder_normalized = normalize_text(folder_name)
                for event_title, event_data in events_by_title.items():
                    event_normalized = normalize_text(event_data['title'])
                    # Try various matching strategies
                    if (folder_name_lower in event_title or 
                        event_title in folder_name_lower or
                        folder_name_lower.replace(' ', '') == event_title.replace(' ', '') or
                        folder_name_lower.replace('-', ' ') == event_title.replace('-', ' ') or
                        folder_normalized == event_normalized or
                        folder_normalized in event_normalized or
                        event_normalized in folder_normalized):
                        matching_event = event_data
                        break
            
            if matching_event:
                # Match found - use full event data including location, tags, date
                gallery_events.append({
                    'id': f"gallery-{matching_event['id']}",
                    'eventTitle': matching_event['title'],
                    'date': matching_event['date_time'].split('T')[0] if matching_event.get('date_time') else '',
                    'location': matching_event.get('location', ''),
                    'tags': matching_event.get('tags', []) or [],  # Ensure it's always an array
                    'photos': images
                })
            else:
                # No matching event - create gallery event from folder name
                # Try to get event details from gallery_images table if event_id exists
                event_details = None
                if images:
                    first_image = images[0]
                    # Check if any image has an event_id linked
                    for img in gallery_images:
                        if img.get('folder_name') == folder_name and img.get('event_id'):
                            # Try to get event details using event_id
                            try:
                                event_details_response = supabase.table('events').select('id, title, date_time, location, tags').eq('id', img.get('event_id')).limit(1).execute()
                                if event_details_response.data and len(event_details_response.data) > 0:
                                    event_details = event_details_response.data[0]
                                    break
                            except Exception as e:
                                logger.warning(f"Could not fetch event details for event_id {img.get('event_id')}: {e}")
                
                if event_details:
                    # Use event details from linked event
                    gallery_events.append({
                        'id': f"gallery-{event_details['id']}",
                        'eventTitle': event_details['title'],
                        'date': event_details['date_time'].split('T')[0] if event_details.get('date_time') else '',
                        'location': event_details.get('location', ''),
                        'tags': event_details.get('tags', []) or [],
                        'photos': images
                    })
                    logger.info(f"Found event details via event_id for folder '{folder_name}'")
                else:
                    # No event match - create gallery event from folder name only
                    gallery_events.append({
                        'id': f"gallery-{folder_name.lower().replace(' ', '-')}",
                        'eventTitle': folder_name,
                        'date': images[0].get('created_at', '').split('T')[0] if images else '',
                        'location': '',
                        'tags': [],
                        'photos': images
                    })
        
        # Filter out images with invalid/empty URLs before returning
        filtered_events = []
        total_valid_images = 0
        for event in gallery_events:
            valid_photos = []
            for photo in event['photos']:
                photo_url = photo.get('url', '').strip()
                # Validate URL format
                if photo_url and (photo_url.startswith('http://') or photo_url.startswith('https://') or photo_url.startswith('/')):
                    valid_photos.append(photo)
                    total_valid_images += 1
            
            if valid_photos:
                event['photos'] = valid_photos
                filtered_events.append(event)
        
        
        return JSONResponse(
            status_code=200,
            content={
                "events": filtered_events,
                "count": len(filtered_events),
                "total_images": total_valid_images
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing gallery images: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list gallery images: {str(e)}"
        )


@gallery_images_router.get("/proxy/{file_id}")
async def proxy_google_drive_image(file_id: str):
    """
    Proxy endpoint to serve Google Drive images with proper CORS headers
    This bypasses CORS issues by serving images from the backend
    
    Args:
        file_id: Google Drive file ID
    
    Returns:
        Image file with proper content-type and CORS headers
    """
    try:
        drive_service = get_google_drive_service()
        if not drive_service:
            raise HTTPException(
                status_code=503,
                detail="Google Drive service not available"
            )
        
        # Download the image from Google Drive
        image_data = drive_service.download_file(file_id)
        
        if not image_data:
            raise HTTPException(
                status_code=404,
                detail=f"Image not found or could not be downloaded (file_id: {file_id})"
            )
        
        # Determine content type based on file extension or default to jpeg
        # We'll use a generic image type since we don't know the exact MIME type
        content_type = "image/jpeg"  # Default, works for most images
        
        # Try to get file metadata to determine actual MIME type
        try:
            file_metadata = drive_service.service.files().get(
                fileId=file_id,
                fields='mimeType'
            ).execute()
            mime_type = file_metadata.get('mimeType', 'image/jpeg')
            if mime_type.startswith('image/'):
                content_type = mime_type
        except Exception as e:
            logger.debug(f"Could not get MIME type for file {file_id}: {e}, using default")
        
        # Return image with proper headers
        return Response(
            content=image_data,
            media_type=content_type,
            headers={
                "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
                "Access-Control-Allow-Origin": "*",  # Allow all origins
                "Access-Control-Allow-Methods": "GET",
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error proxying image {file_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to proxy image: {str(e)}"
        )

