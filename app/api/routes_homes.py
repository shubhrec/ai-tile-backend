"""
User-specific home/room image management endpoints.

Endpoints for persisting and retrieving home images that are linked to authenticated users.
Homes survive page reloads and are accessible across devices and sessions.
"""
import logging
from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from app.services.auth import verify_token
from app.services.supabase_client import supabase

logger = logging.getLogger(__name__)

router = APIRouter()


class AddHomeRequest(BaseModel):
    """Request payload for adding a new home."""
    image_url: str = Field(..., description="Supabase Storage URL of the home image")
    name: Optional[str] = Field(default="", description="Optional name/description for the home")


@router.post("/api/homes", dependencies=[Depends(verify_token)])
async def add_home(request: Request):
    """
    Add a new home for the authenticated user.

    **Authentication Required:** Bearer token in Authorization header

    Args:
        request: FastAPI request (contains authenticated user_id)

    Returns:
        JSON with success status and created home record

    Raises:
        HTTPException 400: If image_url is missing
        HTTPException 401: If authentication fails or user_id missing
        HTTPException 500: If database operation fails
    """
    try:
        # Parse request body
        body = await request.json()
        print("🏠 Incoming /api/homes payload:", body)
        logger.info(f"🏠 Incoming /api/homes payload: {body}")

        # Extract user_id from request state (set by verify_token)
        user_id = request.state.user_id

        # Debug: Check if user_id is present
        if not user_id:
            print("❌ ERROR: User ID missing — token not verified properly")
            logger.error("User ID missing from request.state — auth middleware issue")
            raise HTTPException(
                status_code=401,
                detail="User ID missing — token not verified"
            )

        print(f"✅ User ID extracted: {user_id[:8]}...")
        logger.info(f"🔐 User {user_id[:8]}... adding home")

        # Validate image_url
        image_url = body.get("image_url")
        name = body.get("name", "")

        if not image_url:
            print("❌ ERROR: Missing image_url in request body")
            logger.error("Missing image_url in request body")
            raise HTTPException(
                status_code=400,
                detail="Missing image_url"
            )

        print(f"📝 Inserting home: user_id={user_id[:8]}..., name='{name}', image_url={image_url[:50]}...")
        logger.info(f"📝 Inserting home: user_id={user_id[:8]}..., name='{name}', image_url={image_url[:50]}...")

        # Insert home record
        insert_data = {
            "user_id": user_id,
            "name": name,
            "image_url": image_url
        }

        res = supabase.table("homes").insert(insert_data).execute()

        print("✅ Insert result:", res.data)
        logger.info(f"✅ Insert result: {res.data}")

        if not res.data:
            print("❌ ERROR: No data returned from insert")
            logger.error("No data returned from Supabase insert")
            raise HTTPException(
                status_code=500,
                detail="Failed to insert home record — no data returned"
            )

        home = res.data[0]
        print(f"✅ Home created: ID={home.get('id')} for user {user_id[:8]}...")
        logger.info(f"✅ Home created: ID={home.get('id')} for user {user_id[:8]}...")

        return {
            "success": True,
            "home": home
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error inserting home: {e}")
        logger.error(f"❌ Error adding home: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to add home: {str(e)}"
        )


@router.get("/api/homes", dependencies=[Depends(verify_token)])
async def get_homes(request: Request):
    """
    Get all homes for the authenticated user.

    **Authentication Required:** Bearer token in Authorization header

    Args:
        request: FastAPI request (contains authenticated user_id)

    Returns:
        JSON with list of user's homes, ordered by created_at (newest first)

    Raises:
        HTTPException 401: If authentication fails
        HTTPException 500: If database operation fails
    """
    try:
        user_id = request.state.user_id
        logger.info(f"🔐 User {user_id[:8]}... fetching homes")

        # Query homes for this user
        res = supabase.table("homes")\
            .select("*")\
            .eq("user_id", user_id)\
            .order("created_at", desc=True)\
            .execute()

        homes = res.data if res.data else []
        logger.info(f"✅ Retrieved {len(homes)} homes for user {user_id[:8]}...")

        return {
            "homes": homes
        }

    except Exception as e:
        logger.error(f"❌ Error fetching homes: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch homes: {str(e)}"
        )


@router.get("/api/homes/{home_id}", dependencies=[Depends(verify_token)])
async def get_home_by_id(request: Request, home_id: int):
    """
    Get a single home by its ID (only if owned by the authenticated user).

    **Authentication Required:** Bearer token in Authorization header

    Args:
        request: FastAPI request (contains authenticated user_id)
        home_id: ID of the home to retrieve

    Returns:
        JSON with home data

    Raises:
        HTTPException 401: If authentication fails
        HTTPException 404: If home not found or not owned by user
        HTTPException 500: If database operation fails
    """
    try:
        user_id = request.state.user_id
        logger.info(f"🔐 User {user_id[:8]}... fetching home ID={home_id}")

        # Query home by ID and user_id
        res = supabase.table("homes")\
            .select("*")\
            .eq("id", home_id)\
            .eq("user_id", user_id)\
            .execute()

        if not res.data:
            logger.warning(f"⚠️  Home ID={home_id} not found or not owned by user {user_id[:8]}...")
            raise HTTPException(
                status_code=404,
                detail="Home not found or not owned by user"
            )

        home = res.data[0]
        logger.info(f"✅ Retrieved home ID={home_id} for user {user_id[:8]}...")

        return {
            "home": home
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error fetching home: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch home: {str(e)}"
        )


@router.delete("/api/homes/{home_id}", dependencies=[Depends(verify_token)])
async def delete_home(request: Request, home_id: int):
    """
    Delete a home by its ID (only if owned by the authenticated user).

    **Authentication Required:** Bearer token in Authorization header

    Args:
        request: FastAPI request (contains authenticated user_id)
        home_id: ID of the home to delete

    Returns:
        JSON with success status and deleted home ID

    Raises:
        HTTPException 401: If authentication fails
        HTTPException 404: If home not found or not owned by user
        HTTPException 500: If database operation fails
    """
    try:
        user_id = request.state.user_id
        logger.info(f"🔐 User {user_id[:8]}... attempting to delete home ID={home_id}")

        # Step 1: Verify home exists and belongs to user
        existing = supabase.table("homes")\
            .select("*")\
            .eq("id", home_id)\
            .eq("user_id", user_id)\
            .execute()

        if not existing.data:
            logger.warning(f"⚠️  Home ID={home_id} not found or not owned by user {user_id[:8]}...")
            raise HTTPException(
                status_code=404,
                detail="Home not found or not owned by user"
            )

        home = existing.data[0]
        image_url = home.get("image_url")

        # Step 2: Delete home record from database
        supabase.table("homes")\
            .delete()\
            .eq("id", home_id)\
            .eq("user_id", user_id)\
            .execute()

        logger.info(f"✅ Home ID={home_id} deleted from database for user {user_id[:8]}...")

        # Step 3: Optional - Delete image file from Supabase Storage
        if image_url:
            try:
                # Extract bucket and filename from URL
                url_parts = image_url.split("/")
                if "storage" in url_parts:
                    public_index = url_parts.index("public")
                    if public_index + 2 < len(url_parts):
                        bucket = url_parts[public_index + 1]
                        filename = url_parts[public_index + 2]

                        # Delete from storage
                        supabase.storage.from_(bucket).remove([filename])
                        logger.info(f"✅ File deleted from storage: {bucket}/{filename}")
            except Exception as storage_error:
                # Don't fail the request if storage deletion fails
                logger.warning(f"⚠️  Failed to delete file from storage: {storage_error}")

        return {
            "success": True,
            "deleted_id": home_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error deleting home: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete home: {str(e)}"
        )
