"""
Supabase Storage Service
Handles file uploads to Supabase Storage buckets
"""

import logging
from typing import Optional, Tuple
from datetime import datetime
import uuid
from pathlib import Path
from db.supabase import get_supabase_client

logger = logging.getLogger(__name__)


class SupabaseStorageService:
    """Service for managing file uploads to Supabase Storage"""
    
    # Bucket names
    BUCKET_POSTERS = "event-posters"
    BUCKET_SPEAKERS = "speaker-images"
    BUCKET_EVENTS = "event-images"
    
    # Allowed file extensions
    ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    
    # Max file size (10MB)
    MAX_FILE_SIZE = 10 * 1024 * 1024
    
    def __init__(self):
        self.supabase = get_supabase_client()
    
    def _get_bucket_name(self, image_type: str) -> str:
        """Get bucket name for image type"""
        bucket_map = {
            "poster": self.BUCKET_POSTERS,
            "speaker": self.BUCKET_SPEAKERS,
            "event": self.BUCKET_EVENTS
        }
        return bucket_map.get(image_type, self.BUCKET_EVENTS)
    
    def _generate_filename(self, original_filename: str, image_type: str) -> str:
        """Generate unique filename"""
        file_ext = Path(original_filename).suffix.lower()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        
        if image_type == "poster":
            return f"CSA-SFO-{timestamp}{file_ext}"
        elif image_type == "speaker":
            return f"speaker_{timestamp}_{unique_id}{file_ext}"
        else:  # event
            return f"event_{timestamp}_{unique_id}{file_ext}"
    
    def _is_allowed_file(self, filename: str) -> bool:
        """Check if file extension is allowed"""
        ext = Path(filename).suffix.lower()
        return ext in self.ALLOWED_EXTENSIONS
    
    def upload_image(
        self,
        file_content: bytes,
        original_filename: str,
        image_type: str,
        content_type: str = "image/jpeg"
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Upload image to Supabase Storage
        
        Args:
            file_content: Binary file content
            original_filename: Original filename
            image_type: Type of image (poster, speaker, event)
            content_type: MIME type of the file
        
        Returns:
            Tuple of (success: bool, public_url: str, error_message: str)
        """
        try:
            # Validate file extension
            if not self._is_allowed_file(original_filename):
                return False, None, f"File type not allowed. Allowed types: {', '.join(self.ALLOWED_EXTENSIONS)}"
            
            # Validate file size
            if len(file_content) > self.MAX_FILE_SIZE:
                return False, None, "File size exceeds 10MB limit"
            
            # Generate unique filename
            filename = self._generate_filename(original_filename, image_type)
            
            # Get bucket name
            bucket_name = self._get_bucket_name(image_type)
            
            logger.info(f"Uploading {filename} to bucket {bucket_name}")
            
            # Upload to Supabase Storage
            result = self.supabase.storage.from_(bucket_name).upload(
                path=filename,
                file=file_content,
                file_options={
                    "content-type": content_type,
                    "cache-control": "3600",
                    "upsert": "false"
                }
            )
            
            logger.info(f"Upload result: {result}")
            
            # Get public URL
            public_url = self.supabase.storage.from_(bucket_name).get_public_url(filename)
            
            logger.info(f"File uploaded successfully: {public_url}")
            
            return True, public_url, None
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error uploading to Supabase Storage: {error_msg}")
            
            # Check if file already exists
            if "already exists" in error_msg.lower() or "duplicate" in error_msg.lower():
                # Try to get the existing file's URL
                try:
                    bucket_name = self._get_bucket_name(image_type)
                    filename = self._generate_filename(original_filename, image_type)
                    public_url = self.supabase.storage.from_(bucket_name).get_public_url(filename)
                    return True, public_url, None
                except:
                    pass
            
            return False, None, f"Upload failed: {error_msg}"
    
    def delete_image(self, image_url: str, image_type: str) -> Tuple[bool, Optional[str]]:
        """
        Delete image from Supabase Storage
        
        Args:
            image_url: Full URL or filename of the image
            image_type: Type of image (poster, speaker, event)
        
        Returns:
            Tuple of (success: bool, error_message: str)
        """
        try:
            # Extract filename from URL
            filename = image_url.split('/')[-1]
            bucket_name = self._get_bucket_name(image_type)
            
            logger.info(f"Deleting {filename} from bucket {bucket_name}")
            
            # Delete from Supabase Storage
            result = self.supabase.storage.from_(bucket_name).remove([filename])
            
            logger.info(f"Delete result: {result}")
            
            return True, None
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error deleting from Supabase Storage: {error_msg}")
            return False, error_msg
    
    def list_images(self, image_type: str, limit: int = 100) -> Tuple[bool, list, Optional[str]]:
        """
        List images from Supabase Storage bucket
        
        Args:
            image_type: Type of image (poster, speaker, event)
            limit: Maximum number of files to return
        
        Returns:
            Tuple of (success: bool, files: list, error_message: str)
        """
        try:
            bucket_name = self._get_bucket_name(image_type)
            
            logger.info(f"Listing files from bucket {bucket_name}")
            
            # List files in bucket
            result = self.supabase.storage.from_(bucket_name).list()
            
            # Format file list with public URLs
            files = []
            for file in result[:limit]:
                public_url = self.supabase.storage.from_(bucket_name).get_public_url(file['name'])
                files.append({
                    'name': file['name'],
                    'url': public_url,
                    'size': file.get('metadata', {}).get('size', 0),
                    'created_at': file.get('created_at'),
                    'updated_at': file.get('updated_at')
                })
            
            logger.info(f"Found {len(files)} files in {bucket_name}")
            
            return True, files, None
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error listing files from Supabase Storage: {error_msg}")
            return False, [], error_msg


# Singleton instance
_storage_service = None


def get_storage_service() -> SupabaseStorageService:
    """Get or create storage service instance"""
    global _storage_service
    if _storage_service is None:
        _storage_service = SupabaseStorageService()
    return _storage_service

