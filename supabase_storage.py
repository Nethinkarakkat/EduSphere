"""
Supabase Storage helper functions for profile picture management.
"""
import os
import uuid
import logging
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

# Initialize Supabase client
supabase_url = os.getenv('SUPABASE_URL')
supabase_key = os.getenv('SUPABASE_SERVICE_KEY') or os.getenv('SUPABASE_KEY')

if supabase_url and supabase_key:
    supabase = create_client(supabase_url, supabase_key)
    logger.info(f"Supabase client initialized with URL: {supabase_url}")
else:
    supabase = None
    logger.error("Missing SUPABASE_URL or SUPABASE_SERVICE_KEY - Supabase Storage will not be available")

BUCKET_NAME = 'profile-images'


def check_bucket_exists():
    """
    Check if the profile-images bucket exists in Supabase Storage.
    
    Returns:
        bool: True if bucket exists, False otherwise
    """
    if not supabase:
        logger.error("Cannot check bucket existence - Supabase client not initialized")
        return False
    
    try:
        # Try to list buckets to verify profile-images exists
        buckets = supabase.storage.list_buckets()
        bucket_names = [bucket.name for bucket in buckets]
        
        if BUCKET_NAME in bucket_names:
            logger.info(f"Bucket '{BUCKET_NAME}' exists")
            return True
        else:
            logger.error(f"Bucket '{BUCKET_NAME}' not found. Available buckets: {bucket_names}")
            return False
            
    except Exception as e:
        logger.error(f"Error checking bucket existence: {type(e).__name__}: {e}")
        return False


def upload_profile_picture(file, user_id):
    """
    Upload a profile picture to Supabase Storage.
    
    Args:
        file: File object from request.files
        user_id: User ID for unique naming
    
    Returns:
        str: Public URL of the uploaded file, or None if upload fails
    """
    if not supabase:
        logger.error("Supabase client not initialized - cannot upload profile picture")
        return None
    
    # Check if bucket exists before attempting upload
    if not check_bucket_exists():
        logger.error(f"Bucket '{BUCKET_NAME}' does not exist - cannot upload profile picture")
        return None
    
    try:
        # Generate unique filename
        file_ext = os.path.splitext(file.filename)[1]
        unique_filename = f"{user_id}_{uuid.uuid4().hex}{file_ext}"
        
        logger.info(f"Uploading profile picture - User ID: {user_id}, Filename: {unique_filename}")
        
        # Read file content
        file_content = file.read()
        file_size = len(file_content)
        logger.info(f"File size: {file_size} bytes, Content type: {file.content_type}")
        
        # Upload to Supabase Storage
        result = supabase.storage.from_(BUCKET_NAME).upload(
            path=unique_filename,
            file=file_content,
            file_options={'content-type': file.content_type}
        )
        
        logger.info(f"Upload result: {result}")
        
        # Get public URL
        public_url = supabase.storage.from_(BUCKET_NAME).get_public_url(unique_filename)
        
        logger.info(f"Profile picture uploaded successfully - Public URL: {public_url}")
        return public_url
        
    except Exception as e:
        logger.exception(f"Supabase upload failed - Exception type: {type(e).__name__}, Message: {str(e)}")
        logger.error(f"Upload details - Bucket: {BUCKET_NAME}, User ID: {user_id}, Filename: {unique_filename if 'unique_filename' in locals() else 'N/A'}")
        return None


def delete_profile_picture(storage_path):
    """
    Delete a profile picture from Supabase Storage.
    
    Args:
        storage_path: Storage path or public URL of the file to delete
    """
    if not supabase:
        logger.error("Supabase client not initialized - cannot delete profile picture")
        return
    
    if not storage_path:
        logger.warning("No storage path provided - nothing to delete")
        return
    
    try:
        # Extract filename from URL if it's a full URL
        if storage_path.startswith('http'):
            filename = storage_path.split('/')[-1]
            logger.info(f"Extracted filename from URL: {filename}")
        else:
            filename = storage_path
            logger.info(f"Using storage path directly: {filename}")
        
        logger.info(f"Deleting profile picture from bucket '{BUCKET_NAME}': {filename}")
        
        # Delete from Supabase Storage
        result = supabase.storage.from_(BUCKET_NAME).remove([filename])
        
        logger.info(f"Profile picture deleted successfully - Result: {result}")
        
    except Exception as e:
        logger.exception(f"Supabase delete failed - Exception type: {type(e).__name__}, Message: {str(e)}")
        logger.error(f"Delete details - Bucket: {BUCKET_NAME}, Storage path: {storage_path}")


def get_profile_picture_url(storage_path):
    """
    Get the public URL for a profile picture.
    
    Args:
        storage_path: Storage path or public URL
    
    Returns:
        str: Public URL, or None if invalid
    """
    if not storage_path:
        return None
    
    # If it's already a full URL, return it
    if storage_path.startswith('http'):
        return storage_path
    
    # If it's a local path, return None (will fall back to default)
    if storage_path.startswith('/static/'):
        return None
    
    # If it's a storage path, get public URL
    if supabase:
        try:
            return supabase.storage.from_(BUCKET_NAME).get_public_url(storage_path)
        except:
            return None
    
    return None
