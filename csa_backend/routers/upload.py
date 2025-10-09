from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
import os
import shutil
from pathlib import Path
import uuid
from datetime import datetime
from services.auth_services import verify_token
from config.logging import setup_logging
import logging

setup_logging()
logger = logging.getLogger(__name__)

upload_router = APIRouter()

# Define the base upload directory
# Get the absolute path to the project root, then navigate to frontend
BASE_UPLOAD_DIR = Path(__file__).parent.parent.parent.parent.parent / "frontend" / "csa-sfo-website-frontend" / "public"

# Define upload directories for different image types
UPLOAD_DIRS = {
    "poster": BASE_UPLOAD_DIR / "posters",
    "speaker": BASE_UPLOAD_DIR / "Speaker-images",
    "event": BASE_UPLOAD_DIR / "Events-pictures"
}

# Ensure upload directories exist
for dir_path in UPLOAD_DIRS.values():
    dir_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"Upload directory created/verified: {dir_path}")

# Allowed image extensions
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}

def is_allowed_file(filename: str) -> bool:
    """Check if file extension is allowed."""
    ext = Path(filename).suffix.lower()
    return ext in ALLOWED_EXTENSIONS

@upload_router.post("/upload/image")
async def upload_image(
    file: UploadFile = File(...),
    image_type: str = Query(..., description="Type of image: 'poster', 'speaker', or 'event'"),
    token_data: dict = Depends(verify_token)
):
    """
    Upload an image (poster, speaker, or event).
    Only admins can upload images.
    Returns the URL path to the uploaded image.
    
    Parameters:
    - file: The image file to upload
    - image_type: Type of image - 'poster' (event posters), 'speaker' (speaker images), or 'event' (general event images)
    """
    logger.info(f"=== UPLOAD REQUEST RECEIVED ===")
    logger.info(f"File: {file.filename}, Type: {image_type}, User: {token_data.get('email')}")
    try:
        # Validate image type
        if image_type not in UPLOAD_DIRS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid image_type. Must be one of: {', '.join(UPLOAD_DIRS.keys())}"
            )
        
        # Verify the file is an image
        if not is_allowed_file(file.filename):
            raise HTTPException(
                status_code=400,
                detail=f"File type not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
            )
        
        # Verify file size (limit to 10MB)
        contents = await file.read()
        file_size = len(contents)
        if file_size > 10 * 1024 * 1024:  # 10MB limit
            raise HTTPException(
                status_code=400,
                detail="File size exceeds 10MB limit"
            )
        
        # Generate unique filename based on image type
        file_ext = Path(file.filename).suffix.lower()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        
        # Use different naming conventions for different types
        if image_type == "poster":
            new_filename = f"CSA-SFO-{timestamp}{file_ext}"
        elif image_type == "speaker":
            new_filename = f"speaker_{timestamp}_{unique_id}{file_ext}"
        else:  # event
            new_filename = f"event_{timestamp}_{unique_id}{file_ext}"
        
        # Get the appropriate upload directory
        upload_dir = UPLOAD_DIRS[image_type]
        file_path = upload_dir / new_filename
        
        logger.info(f"Attempting to save file to: {file_path}")
        logger.info(f"Upload directory exists: {upload_dir.exists()}")
        logger.info(f"Upload directory is writable: {os.access(upload_dir, os.W_OK)}")
        
        # Write the file
        with open(file_path, "wb") as buffer:
            buffer.write(contents)
        
        # Verify file was written
        if file_path.exists():
            logger.info(f"File successfully written to: {file_path} (size: {file_path.stat().st_size} bytes)")
        else:
            logger.error(f"File was NOT written to: {file_path}")
        
        # Return the public URL path based on image type
        folder_names = {
            "poster": "posters",
            "speaker": "Speaker-images",
            "event": "Events-pictures"
        }
        public_url = f"/{folder_names[image_type]}/{new_filename}"
        
        logger.info(f"{image_type.capitalize()} image uploaded successfully by {token_data.get('email')}: {public_url}")
        
        return JSONResponse(
            status_code=200,
            content={
                "message": "File uploaded successfully",
                "url": public_url,
                "filename": new_filename,
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

