"""
File upload and retrieval endpoints for Supabase Storage.
"""
import os
import time
from fastapi import APIRouter, UploadFile, File, HTTPException, Path
from supabase import create_client, Client
from typing import List


router = APIRouter()


def get_supabase_client() -> Client:
    """Initialize and return Supabase client."""
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not supabase_key:
        raise HTTPException(
            status_code=500,
            detail="Supabase credentials not configured on server"
        )

    return create_client(supabase_url, supabase_key)


@router.post("/upload/{bucket}")
async def upload_file(
    bucket: str = Path(..., description="Bucket name (e.g., 'tiles', 'homes', 'generated')"),
    file: UploadFile = File(..., description="Image file to upload")
):
    """
    Upload an image file to Supabase Storage.

    Args:
        bucket: The storage bucket name
        file: Image file (multipart/form-data)

    Returns:
        JSON with success status and public URL
    """
    try:
        # Validate file is an image
        if not file.content_type or not file.content_type.startswith("image/"):
            raise HTTPException(
                status_code=400,
                detail="Only image files are allowed"
            )

        # Initialize Supabase client
        supabase = get_supabase_client()

        # Read file bytes
        file_bytes = await file.read()

        # Generate unique filename with timestamp
        file_name = f"{int(time.time())}_{file.filename}"

        # Upload to Supabase Storage
        try:
            result = supabase.storage.from_(bucket).upload(
                file_name,
                file_bytes,
                file_options={"content-type": file.content_type}
            )
            print(f"✅ File uploaded: {file_name} to bucket '{bucket}'")
        except Exception as upload_error:
            print(f"❌ Upload error: {upload_error}")
            raise HTTPException(
                status_code=400,
                detail=f"Upload failed: {str(upload_error)}"
            )

        # Get public URL
        public_url = supabase.storage.from_(bucket).get_public_url(file_name)

        return {
            "success": True,
            "url": public_url
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Unexpected error in upload: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/list/{bucket}")
async def list_files(
    bucket: str = Path(..., description="Bucket name (e.g., 'tiles', 'homes', 'generated')")
):
    """
    List all files in a Supabase Storage bucket.

    Args:
        bucket: The storage bucket name

    Returns:
        JSON with success status and list of public URLs
    """
    try:
        # Initialize Supabase client
        supabase = get_supabase_client()

        # List all files in the bucket
        try:
            result = supabase.storage.from_(bucket).list()

            # Extract file data
            if hasattr(result, 'data') and result.data:
                files_data = result.data
            elif isinstance(result, list):
                files_data = result
            else:
                files_data = []

            # Generate public URLs for all files
            urls = []
            for item in files_data:
                if isinstance(item, dict) and 'name' in item:
                    file_name = item['name']
                    public_url = supabase.storage.from_(bucket).get_public_url(file_name)
                    urls.append(public_url)

            print(f"✅ Listed {len(urls)} files from bucket '{bucket}'")

            return {
                "success": True,
                "files": urls
            }

        except Exception as list_error:
            print(f"❌ List error: {list_error}")
            raise HTTPException(
                status_code=400,
                detail=f"Failed to list files: {str(list_error)}"
            )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Unexpected error in list: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "files": []
        }
