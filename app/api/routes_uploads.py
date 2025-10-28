"""
File upload and retrieval endpoints for Supabase Storage.
"""
import os
import time
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException, Path, Request, Depends
from typing import List
from app.services.auth import verify_token
from app.services.supabase_client import supabase

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/upload/{bucket}", dependencies=[Depends(verify_token)])
async def upload_file(
    request: Request,
    bucket: str = Path(..., description="Bucket name (e.g., 'tiles', 'homes', 'generated')"),
    file: UploadFile = File(..., description="Image file to upload")
):
    """
    Upload an image file to Supabase Storage.

    **Authentication Required:** Bearer token in Authorization header

    Args:
        request: FastAPI request (contains authenticated user_id)
        bucket: The storage bucket name
        file: Image file (multipart/form-data)

    Returns:
        JSON with success status and public URL
    """
    try:
        # Extract authenticated user ID
        user_id = request.state.user_id
        logger.info(f"🔐 User {user_id[:8]}... uploading to bucket '{bucket}'")

        # Validate file is an image
        if not file.content_type or not file.content_type.startswith("image/"):
            raise HTTPException(
                status_code=400,
                detail="Only image files are allowed"
            )

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
            logger.info(f"✅ File uploaded by {user_id[:8]}...: {file_name} to bucket '{bucket}'")
        except Exception as upload_error:
            logger.error(f"❌ Upload error: {upload_error}")
            raise HTTPException(
                status_code=400,
                detail=f"Upload failed: {str(upload_error)}"
            )

        # Get optimized public URL with CDN caching and compression
        SUPABASE_URL = os.getenv("SUPABASE_URL")
        public_url = f"{SUPABASE_URL}/storage/v1/render/image/public/{bucket}/{file_name}?width=512&quality=80"

        return {
            "success": True,
            "url": public_url
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error in upload: {str(e)}")
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

            # Generate optimized public URLs for all files with CDN caching
            SUPABASE_URL = os.getenv("SUPABASE_URL")
            urls = []
            for item in files_data:
                if isinstance(item, dict) and 'name' in item:
                    file_name = item['name']
                    public_url = f"{SUPABASE_URL}/storage/v1/render/image/public/{bucket}/{file_name}?width=512&quality=80"
                    urls.append(public_url)

            logger.info(f"✅ Listed {len(urls)} files from bucket '{bucket}'")

            return {
                "success": True,
                "files": urls
            }

        except Exception as list_error:
            logger.error(f"❌ List error: {list_error}")
            raise HTTPException(
                status_code=400,
                detail=f"Failed to list files: {str(list_error)}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error in list: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "files": []
        }
