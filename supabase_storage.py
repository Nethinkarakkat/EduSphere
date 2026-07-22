"""
Supabase Storage helper functions for profile picture management.
"""
import os
import uuid
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

# Initialize Supabase client
supabase_url = os.getenv('SUPABASE_URL')
supabase_key = os.getenv('SUPABASE_KEY')

if supabase_url and supabase_key:
    supabase = create_client(supabase_url, supabase_key)
else:
    supabase = None

BUCKET_NAME = 'profile-images'


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
        return None
    
    try:
        # Generate unique filename
        file_ext = os.path.splitext(file.filename)[1]
        unique_filename = f"{user_id}_{uuid.uuid4().hex}{file_ext}"
        
        # Read file content
        file_content = file.read()
        
        # Upload to Supabase Storage
        result = supabase.storage.from_(BUCKET_NAME).upload(
            path=unique_filename,
            file=file_content,
            file_options={'content-type': file.content_type}
        )
        
        # Get public URL
        public_url = supabase.storage.from_(BUCKET_NAME).get_public_url(unique_filename)
        
        return public_url
        
    except Exception as e:
        print(f"Error uploading to Supabase: {e}")
        return None


def delete_profile_picture(storage_path):
    """
    Delete a profile picture from Supabase Storage.
    
    Args:
        storage_path: Storage path or public URL of the file to delete
    """
    if not supabase or not storage_path:
        return
    
    try:
        # Extract filename from URL if it's a full URL
        if storage_path.startswith('http'):
            filename = storage_path.split('/')[-1]
        else:
            filename = storage_path
        
        # Delete from Supabase Storage
        supabase.storage.from_(BUCKET_NAME).remove([filename])
        
    except Exception as e:
        print(f"Error deleting from Supabase: {e}")


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
