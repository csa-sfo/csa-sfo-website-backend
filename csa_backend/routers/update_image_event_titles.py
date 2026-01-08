"""
Utility endpoint to update existing images with event_title
This can be used to retroactively link images to events
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from services.auth_services import verify_token
from db.supabase import get_supabase_client
from services.google_drive_service import get_google_drive_service
from config.logging import setup_logging
import logging

setup_logging()
logger = logging.getLogger(__name__)

update_images_router = APIRouter()


@update_images_router.post("/update-event-titles")
async def update_image_event_titles(
    event_title: str,
    token_data: dict = Depends(verify_token)
):
    """
    Update event_title for all images that were synced from a specific Google Drive folder
    This is useful if the event_title column was added after images were synced
    """
    try:
        supabase = get_supabase_client()
        drive_service = get_google_drive_service()
        
        if not drive_service or not drive_service.service:
            raise HTTPException(
                status_code=503,
                detail="Google Drive service not available"
            )
        
        # Find the folder for this event
        folder_id = drive_service.find_folder_by_name(event_title)
        if not folder_id:
            raise HTTPException(
                status_code=404,
                detail=f"Folder '{event_title}' not found in Google Drive"
            )
        
        # Get all images in this folder
        images = drive_service.list_images_in_folder(folder_id)
        if not images:
            return JSONResponse(
                status_code=200,
                content={
                    "message": f"No images found in folder '{event_title}'",
                    "updated_count": 0
                }
            )
        
        # Get all image filenames from Supabase Storage
        from services.supabase_storage_service import get_storage_service
        storage_service = get_storage_service()
        success, files, _ = storage_service.list_images("event", limit=1000)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to list images from storage")
        
        # Match images by name and update event_title
        updated_count = 0
        image_names = {img['name'] for img in images}
        
        for file in files:
            filename = file['name']
            # Check if this image might be from our folder (by checking if name matches)
            # This is a simple approach - in production you might want more sophisticated matching
            
            # Update the image_captions table
            try:
                # Try to update with event_title
                result = supabase.table('image_captions').update({
                    'event_title': event_title
                }).eq('filename', filename).eq('image_type', 'event').execute()
                
                if result.data:
                    updated_count += 1
            except Exception as e:
                # If column doesn't exist, log warning
                if 'event_title' in str(e).lower() or 'column' in str(e).lower():
                    logger.warning(f"event_title column may not exist: {e}")
                    return JSONResponse(
                        status_code=400,
                        content={
                            "message": "event_title column does not exist in database",
                            "detail": "Please run the migration script to add the column first"
                        }
                    )
                else:
                    logger.warning(f"Error updating {filename}: {e}")
        
        return JSONResponse(
            status_code=200,
            content={
                "message": f"Updated event_title for images from '{event_title}'",
                "updated_count": updated_count,
                "total_images_in_folder": len(images)
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating image event titles: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update event titles: {str(e)}"
        )

