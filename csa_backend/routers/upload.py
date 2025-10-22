from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from pathlib import Path
from services.auth_services import verify_token
from services.supabase_storage_service import get_storage_service
from config.logging import setup_logging
import logging

setup_logging()
logger = logging.getLogger(__name__)

upload_router = APIRouter()

@upload_router.post("/upload/image")
async def upload_image(
    file: UploadFile = File(...),
    image_type: str = Query(..., description="Type of image: 'poster', 'speaker', or 'event'"),
    token_data: dict = Depends(verify_token)
):
    """
    Upload an image to Supabase Storage.
    Only authenticated users can upload images.
    Returns the public URL to the uploaded image.
    
    Parameters:
    - file: The image file to upload
    - image_type: Type of image - 'poster' (event posters), 'speaker' (speaker images), or 'event' (general event images)
    """
    logger.info(f"=== SUPABASE UPLOAD REQUEST RECEIVED ===")
    logger.info(f"File: {file.filename}, Type: {image_type}, User: {token_data.get('email')}")
    
    try:
        # Validate image type
        valid_types = ["poster", "speaker", "event"]
        if image_type not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid image_type. Must be one of: {', '.join(valid_types)}"
            )
        
        # Read file content
        contents = await file.read()
        
        # Determine content type
        content_type = file.content_type or "image/jpeg"
        
        # Get storage service
        storage_service = get_storage_service()
        
        # Upload to Supabase
        success, public_url, error_message = storage_service.upload_image(
            file_content=contents,
            original_filename=file.filename,
            image_type=image_type,
            content_type=content_type
        )
        
        if not success:
            raise HTTPException(
                status_code=400,
                detail=error_message or "Failed to upload image"
            )
        
        logger.info(f"{image_type.capitalize()} image uploaded successfully by {token_data.get('email')}: {public_url}")
        
        return JSONResponse(
            status_code=200,
            content={
                "message": "File uploaded successfully to Supabase Storage",
                "url": public_url,
                "filename": public_url.split('/')[-1],
                "image_type": image_type
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading file: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload file: {str(e)}"
        )

