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
from db.supabase import get_supabase_client
from config.logging import setup_logging
import logging

setup_logging()
logger = logging.getLogger(__name__)

event_images_router = APIRouter()


class EventImageCreate(BaseModel):
    url: str
    caption: Optional[str] = None


@event_images_router.get("")
async def list_event_images():
    """
    List all event images from Supabase Storage (Public endpoint - no auth required)
    """
    try:
        storage_service = get_storage_service()
        success, files, error_message = storage_service.list_images("event", limit=100)
        
        if not success:
            raise HTTPException(status_code=500, detail=error_message or "Failed to list images")
        
        # Get captions from database (using existing image_captions table)
        supabase = get_supabase_client()
        try:
            captions_response = supabase.table('image_captions').select('*').eq('image_type', 'event').execute()
            # Build dict using filename from URL as key
            captions_dict = {}
            for item in captions_response.data if captions_response.data else []:
                # Match by filename in the URL
                captions_dict[item['filename']] = item['caption']
        except Exception as e:
            logger.warning(f"Could not fetch captions: {e}")
            captions_dict = {}
        
        # Merge captions with file data
        images_with_captions = []
        for file in files:
            # Extract filename from the file name
            filename = file['name']
            images_with_captions.append({
                'url': file['url'],
                'name': file['name'],
                'size': file['size'],
                'created_at': file.get('created_at'),
                'caption': captions_dict.get(filename, '')
            })
        
        return JSONResponse(
            status_code=200,
            content={
                "images": images_with_captions,
                "count": len(images_with_captions)
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

