"""
Google Drive Service
Handles fetching images from Google Drive folders based on event titles
"""

import logging
import os
import io
import json
from typing import List, Tuple, Optional
from pathlib import Path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError
import pickle
from config.settings import (
    GOOGLE_DRIVE_CLIENT_ID,
    GOOGLE_DRIVE_CLIENT_SECRET,
    GOOGLE_DRIVE_CREDENTIALS_FILE,
    GOOGLE_DRIVE_FOLDER_ID
)

logger = logging.getLogger(__name__)

# Google Drive API scopes
# drive.readonly for reading files, drive for setting permissions
SCOPES = [
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/drive'  # Needed to make files public
]

# Supported image MIME types
IMAGE_MIME_TYPES = [
    'image/jpeg',
    'image/jpg',
    'image/png',
    'image/gif',
    'image/webp',
    'image/bmp'
]


class GoogleDriveService:
    """Service for interacting with Google Drive API"""
    
    def __init__(self):
        self.service = None
        self.client_id = GOOGLE_DRIVE_CLIENT_ID
        self.client_secret = GOOGLE_DRIVE_CLIENT_SECRET
        self.credentials_file = GOOGLE_DRIVE_CREDENTIALS_FILE
        self.root_folder_id = GOOGLE_DRIVE_FOLDER_ID
        self._authenticate()
    
    def _get_client_config(self) -> Optional[dict]:
        """Get OAuth client configuration from environment variables or JSON file"""
        # Try environment variables first
        if self.client_id and self.client_secret:
            logger.info("Using Google Drive credentials from environment variables")
            # For manual OAuth flow, use urn:ietf:wg:oauth:2.0:oob (out-of-band)
            # This allows copy-paste of authorization code
            redirect_uri = os.getenv('GOOGLE_DRIVE_REDIRECT_URI', 'http://localhost')
            return {
                "installed": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                    "redirect_uris": [redirect_uri, "urn:ietf:wg:oauth:2.0:oob", "http://localhost"]
                }
            }
        
        # Fallback to JSON file
        if self.credentials_file and os.path.exists(self.credentials_file):
            logger.info(f"Using Google Drive credentials from file: {self.credentials_file}")
            try:
                with open(self.credentials_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error reading credentials file: {e}")
                return None
        
        return None
    
    def _authenticate(self):
        """Authenticate with Google Drive API"""
        creds = None
        # Allow token file path to be configured via environment variable (for production)
        token_file = os.getenv('GOOGLE_DRIVE_TOKEN_FILE', 'token.pickle')
        
        # Load existing token if available
        if os.path.exists(token_file):
            try:
                with open(token_file, 'rb') as token:
                    creds = pickle.load(token)
            except Exception as e:
                logger.warning(f"Could not load existing token: {e}")
        
        # If there are no (valid) credentials available, let the user log in
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    # Save refreshed token
                    try:
                        with open(token_file, 'wb') as token:
                            pickle.dump(creds, token)
                        logger.info("Token refreshed successfully")
                    except Exception as e:
                        logger.warning(f"Could not save refreshed token: {e}")
                except Exception as e:
                    logger.error(f"Error refreshing credentials: {e}")
                    creds = None
            
            if not creds:
                client_config = self._get_client_config()
                if not client_config:
                    logger.error("Google Drive credentials not found")
                    logger.info("Please set either:")
                    logger.info("  - CSA_GOOGLE_DRIVE_CLIENT_ID and CSA_GOOGLE_DRIVE_CLIENT_SECRET")
                    logger.info("  - OR CSA_GOOGLE_DRIVE_CREDENTIALS_FILE (path to JSON file)")
                    return
                
                # Check if we're in a production environment (no display/server environment)
                # Also check if running in Docker/container (no TTY)
                is_production = (
                    os.getenv('ENVIRONMENT') == 'production' or 
                    not os.getenv('DISPLAY') or
                    os.getenv('GOOGLE_DRIVE_AUTH_CODE')  # If auth code is provided, use manual flow
                )
                
                try:
                    flow = InstalledAppFlow.from_client_config(
                        client_config, SCOPES)
                    
                    if is_production and not os.getenv('GOOGLE_DRIVE_AUTH_CODE'):
                        # For production: show manual auth URL using out-of-band redirect
                        logger.info("=" * 60)
                        logger.info("PRODUCTION AUTHENTICATION REQUIRED")
                        logger.info("=" * 60)
                        logger.info("Please visit the following URL to authorize:")
                        # Use out-of-band redirect for manual copy-paste flow
                        auth_url, _ = flow.authorization_url(
                            prompt='consent', 
                            access_type='offline',
                            redirect_uri='urn:ietf:wg:oauth:2.0:oob'
                        )
                        logger.info(f"\n{auth_url}\n")
                        logger.info("After authorization, Google will show you an authorization code.")
                        logger.info("Copy that code and set it as:")
                        logger.info("  export GOOGLE_DRIVE_AUTH_CODE=<paste_code_here>")
                        logger.info("Then restart the server.")
                        logger.info("=" * 60)
                        return
                    elif os.getenv('GOOGLE_DRIVE_AUTH_CODE'):
                        # Auth code provided - complete authentication
                        auth_code = os.getenv('GOOGLE_DRIVE_AUTH_CODE')
                        creds = flow.fetch_token(
                            code=auth_code,
                            redirect_uri='urn:ietf:wg:oauth:2.0:oob'
                        )
                        logger.info("Authentication successful using provided auth code")
                        # Clear the env var after use (optional, for security)
                        # os.environ.pop('GOOGLE_DRIVE_AUTH_CODE', None)
                    else:
                        # For local development: use browser flow
                        creds = flow.run_local_server(port=0)
                except Exception as e:
                    logger.error(f"Error during authentication: {e}")
                    return
            
            # Save the credentials for the next run
            if creds:
                try:
                    with open(token_file, 'wb') as token:
                        pickle.dump(creds, token)
                    logger.info(f"Credentials saved to {token_file}")
                except Exception as e:
                    logger.warning(f"Could not save token: {e}")
        
        if creds:
            try:
                self.service = build('drive', 'v3', credentials=creds)
                logger.info("Google Drive API authenticated successfully")
            except Exception as e:
                logger.error(f"Error building Drive service: {e}")
    
    def find_folder_by_name(self, folder_name: str, parent_folder_id: Optional[str] = None) -> Optional[str]:
        """
        Find a folder by name in Google Drive
        
        Args:
            folder_name: Name of the folder to find
            parent_folder_id: Optional parent folder ID to search within
        
        Returns:
            Folder ID if found, None otherwise
        """
        if not self.service:
            logger.error("Google Drive service not authenticated")
            return None
        
        try:
            # Build query
            query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            
            if parent_folder_id:
                query += f" and '{parent_folder_id}' in parents"
            elif self.root_folder_id:
                query += f" and '{self.root_folder_id}' in parents"
            
            # Search for folder
            results = self.service.files().list(
                q=query,
                fields="files(id, name)",
                pageSize=10
            ).execute()
            
            folders = results.get('files', [])
            
            if folders:
                folder_id = folders[0]['id']
                return folder_id
            else:
                logger.warning(f"Folder '{folder_name}' not found")
                return None
                
        except HttpError as error:
            logger.error(f"An error occurred while searching for folder: {error}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error finding folder: {e}")
            return None
    
    def list_images_in_folder(self, folder_id: str) -> List[dict]:
        """
        List all image files in a Google Drive folder
        
        Args:
            folder_id: ID of the folder to search
        
        Returns:
            List of image file metadata dictionaries
        """
        if not self.service:
            logger.error("Google Drive service not authenticated")
            return []
        
        images = []
        
        try:
            # Build query for image files
            mime_types_query = " or ".join([f"mimeType='{mime}'" for mime in IMAGE_MIME_TYPES])
            query = f"'{folder_id}' in parents and ({mime_types_query}) and trashed=false"
            
            # List files
            results = self.service.files().list(
                q=query,
                fields="files(id, name, mimeType, size, modifiedTime)",
                pageSize=1000
            ).execute()
            
            files = results.get('files', [])
            
            for file in files:
                images.append({
                    'id': file['id'],
                    'name': file['name'],
                    'mime_type': file.get('mimeType', ''),
                    'size': int(file.get('size', 0)),
                    'modified_time': file.get('modifiedTime', '')
                })
            
            return images
            
        except HttpError as error:
            logger.error(f"An error occurred while listing images: {error}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error listing images: {e}")
            return []
    
    def download_file(self, file_id: str) -> Optional[bytes]:
        """
        Download a file from Google Drive
        
        Args:
            file_id: ID of the file to download
        
        Returns:
            File content as bytes, or None if download fails
        """
        if not self.service:
            logger.error("Google Drive service not authenticated")
            return None
        
        try:
            request = self.service.files().get_media(fileId=file_id)
            file_content = io.BytesIO()
            downloader = MediaIoBaseDownload(file_content, request)
            
            done = False
            while done is False:
                status, done = downloader.next_chunk()
            
            file_content.seek(0)
            return file_content.read()
            
        except HttpError as error:
            logger.error(f"An error occurred while downloading file {file_id}: {error}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error downloading file: {e}")
            return None
    
    def make_file_public(self, file_id: str) -> bool:
        """
        Make a Google Drive file publicly accessible
        
        Args:
            file_id: Google Drive file ID
        
        Returns:
            True if successful, False otherwise
        """
        if not self.service:
            logger.error("Google Drive service not authenticated")
            return False
        
        try:
            # Check if file is already public
            file = self.service.files().get(
                fileId=file_id,
                fields='permissions,name'
            ).execute()
            
            file_name = file.get('name', 'unknown')
            
            # Check if 'anyone' permission already exists
            permissions = file.get('permissions', [])
            for perm in permissions:
                if perm.get('type') == 'anyone' and perm.get('role') == 'reader':
                    return True
            
            # Create a permission that makes the file publicly viewable
            permission = {
                'type': 'anyone',
                'role': 'reader'
            }
            
            result = self.service.permissions().create(
                fileId=file_id,
                body=permission,
                fields='id'
            ).execute()
            
            # Verify the permission was created
            if result.get('id'):
                return True
            else:
                logger.warning(f"⚠ Permission created but no ID returned for file '{file_name}' ({file_id})")
                return False
            
        except HttpError as error:
            error_str = str(error)
            # If permission already exists, that's fine
            if 'already exists' in error_str.lower() or 'duplicate' in error_str.lower():
                return True
            
            # Check for permission denied errors
            if '403' in error_str or 'permission' in error_str.lower() or 'forbidden' in error_str.lower():
                logger.error(f"✗ Permission denied: Cannot make file {file_id} public. Error: {error}")
                logger.error(f"  This usually means:")
                logger.error(f"  1. The OAuth token doesn't have 'drive' scope (needs full drive access, not just readonly)")
                logger.error(f"  2. The file is owned by someone else and you don't have permission to change sharing")
                logger.error(f"  3. The file is in a restricted folder")
                return False
            
            logger.warning(f"⚠ Error making file public: {error}")
            return False
        except Exception as e:
            logger.error(f"✗ Unexpected error making file public: {e}", exc_info=True)
            return False
    
    def get_public_url(self, file_id: str, use_proxy: bool = True) -> Optional[str]:
        """
        Get public URL for a Google Drive file that works for embedding in img tags
        
        Args:
            file_id: Google Drive file ID
            use_proxy: If True, return proxy URL to bypass CORS issues. If False, return direct Drive URL.
        
        Returns:
            Public URL string, or None if failed
        """
        if not self.service:
            logger.error("Google Drive service not authenticated")
            return None
        
        # Use proxy URL to bypass CORS issues
        if use_proxy:
            return f"/v1/routes/gallery-images/proxy/{file_id}"
        
        # Legacy: Direct Google Drive URLs (may have CORS issues)
        try:
            # Try to get webContentLink from the API
            try:
                file_metadata = self.service.files().get(
                    fileId=file_id,
                    fields='webContentLink,thumbnailLink'
                ).execute()
                
                # Prefer webContentLink if available
                web_content_link = file_metadata.get('webContentLink')
                if web_content_link:
                    if 'export=download' in web_content_link:
                        web_content_link = web_content_link.replace('export=download', 'export=view')
                    return web_content_link
                
                # Fallback to thumbnailLink if available
                thumbnail_link = file_metadata.get('thumbnailLink')
                if thumbnail_link:
                    return thumbnail_link
            except Exception:
                pass
            
            # Fallback: Use standard Drive URL
            return f"https://drive.google.com/uc?export=view&id={file_id}"
            
        except HttpError as error:
            logger.warning(f"Error getting file metadata for {file_id}: {error}")
            return f"https://drive.google.com/uc?export=view&id={file_id}"
        except Exception as e:
            logger.error(f"Unexpected error getting public URL: {e}")
            return f"https://drive.google.com/uc?export=view&id={file_id}"
    
    def get_images_from_event_folder(self, event_title: str) -> List[Tuple[str, str, str]]:
        """
        Get all images from a folder named after the event title
        Returns public URLs instead of downloading file content
        
        Args:
            event_title: Title of the event (used as folder name)
        
        Returns:
            List of tuples (filename, public_url, drive_file_id)
        """
        if not self.service:
            logger.error("Google Drive service not authenticated")
            return []
        
        # Find folder by event title
        folder_id = self.find_folder_by_name(event_title)
        if not folder_id:
            logger.warning(f"Could not find folder for event: {event_title}")
            return []
        
        # List images in folder
        images = self.list_images_in_folder(folder_id)
        if not images:
            return []
        
        # Get public URLs for images (make them public if needed)
        image_urls = []
        for image in images:
            
            # Make file public (with retry if needed)
            public_success = self.make_file_public(image['id'])
            if not public_success:
                logger.warning(f"⚠ Failed to make file public: {image['name']} (ID: {image['id']})")
                # Still try to get URL - might work if already public
            
            # Get public URL (try even if make_file_public failed - file might already be public)
            public_url = self.get_public_url(image['id'])
            if public_url:
                image_urls.append((image['name'], public_url, image['id']))
            else:
                logger.error(f"✗ Failed to get public URL for: {image['name']} (ID: {image['id']})")
                # Log the file ID for debugging
                logger.error(f"  File ID: {image['id']} - Check if file exists and is accessible")
            
            # If make_file_public failed, log instructions for manual sharing
            if not public_success and public_url:
                logger.warning(f"⚠ File '{image['name']}' may not be publicly accessible")
                logger.warning(f"  If images show 403 errors, manually share the file in Google Drive:")
                logger.warning(f"  1. Go to: https://drive.google.com/file/d/{image['id']}/view")
                logger.warning(f"  2. Click 'Share' → 'Change to anyone with the link' → 'Viewer'")
                logger.warning(f"  3. Then re-sync the folder")
        
        return image_urls


# Singleton instance
_drive_service = None


def get_google_drive_service() -> Optional[GoogleDriveService]:
    """Get or create Google Drive service instance"""
    global _drive_service
    if _drive_service is None:
        _drive_service = GoogleDriveService()
    return _drive_service if _drive_service.service else None

