"""
User-specific tile management endpoints.

Endpoints for persisting and retrieving tiles that are linked to authenticated users.
Tiles survive page reloads and are accessible across devices and sessions.
"""
import logging
from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from app.services.auth import verify_token
from app.services.supabase_client import supabase

logger = logging.getLogger(__name__)

router = APIRouter()


class AddTileRequest(BaseModel):
    """Request payload for adding a new tile."""
    image_url: str = Field(..., description="Supabase Storage URL of the tile image")
    name: Optional[str] = Field(default="", description="Optional name/description for the tile")
    size: Optional[str] = Field(default=None, max_length=50, description="Optional tile size (e.g., '600x600 mm')")
    price: Optional[float] = Field(default=None, ge=0, description="Optional tile price (must be positive)")
    add_catalog: Optional[bool] = Field(default=True, description="Whether to add to catalog (True) or keep as temporary (False)")


class UpdateTileRequest(BaseModel):
    """Request payload for updating an existing tile."""
    name: Optional[str] = Field(default=None, description="Optional name/description for the tile")
    size: Optional[str] = Field(default=None, max_length=50, description="Optional tile size (e.g., '600x600 mm')")
    price: Optional[float] = Field(default=None, ge=0, description="Optional tile price (must be positive)")
    add_catalog: Optional[bool] = Field(default=None, description="Whether to add to catalog (True) or keep as temporary (False)")


@router.post("/api/tiles", dependencies=[Depends(verify_token)])
async def add_tile(request: Request, body: AddTileRequest):
    """
    Add a new tile for the authenticated user.

    **Authentication Required:** Bearer token in Authorization header

    Args:
        request: FastAPI request (contains authenticated user_id)
        body: Tile data (image_url, optional name, size, price)

    Returns:
        JSON with success status and created tile record

    Raises:
        HTTPException 400: If image_url is missing or validation fails
        HTTPException 401: If authentication fails
        HTTPException 422: If size exceeds 50 chars or price is negative
        HTTPException 500: If database operation fails
    """
    try:
        user_id = request.state.user_id
        logger.info(f"🔐 User {user_id[:8]}... adding tile: {body.name or 'Unnamed'}")

        # Insert tile record
        tile_data = {
            "user_id": user_id,
            "name": body.name or "",
            "image_url": body.image_url,
            "add_catalog": body.add_catalog if body.add_catalog is not None else True,
        }

        # Add optional fields if provided
        if body.size is not None:
            tile_data["size"] = body.size
        if body.price is not None:
            tile_data["price"] = body.price

        res = supabase.table("tiles").insert(tile_data).execute()

        if not res.data:
            raise HTTPException(
                status_code=500,
                detail="Failed to insert tile record"
            )

        tile = res.data[0]
        logger.info(f"✅ Tile created: ID={tile.get('id')} for user {user_id[:8]}...")

        return {
            "success": True,
            "tile": tile
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error adding tile: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to add tile: {str(e)}"
        )


@router.get("/api/tiles", dependencies=[Depends(verify_token)])
async def get_tiles(request: Request):
    """
    Get all tiles for the authenticated user.

    **Authentication Required:** Bearer token in Authorization header

    Args:
        request: FastAPI request (contains authenticated user_id)

    Returns:
        JSON with list of user's tiles, ordered by created_at (newest first)

    Raises:
        HTTPException 401: If authentication fails
        HTTPException 500: If database operation fails
    """
    try:
        user_id = request.state.user_id
        logger.info(f"🔐 User {user_id[:8]}... fetching tiles")

        # Query tiles for this user
        res = supabase.table("tiles")\
            .select("*")\
            .eq("user_id", user_id)\
            .order("created_at", desc=True)\
            .execute()

        tiles = res.data if res.data else []
        logger.info(f"✅ Retrieved {len(tiles)} tiles for user {user_id[:8]}...")

        return {
            "tiles": tiles
        }

    except Exception as e:
        logger.error(f"❌ Error fetching tiles: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch tiles: {str(e)}"
        )


@router.get("/api/tiles/{tile_id}", dependencies=[Depends(verify_token)])
async def get_tile_by_id(request: Request, tile_id: int):
    """
    Get a single tile by its ID (only if owned by the authenticated user).

    **Authentication Required:** Bearer token in Authorization header

    Args:
        request: FastAPI request (contains authenticated user_id)
        tile_id: ID of the tile to retrieve

    Returns:
        JSON with tile data

    Raises:
        HTTPException 401: If authentication fails
        HTTPException 404: If tile not found or not owned by user
        HTTPException 500: If database operation fails
    """
    try:
        user_id = request.state.user_id
        logger.info(f"🔐 User {user_id[:8]}... fetching tile ID={tile_id}")

        # Query tile by ID and user_id
        res = supabase.table("tiles")\
            .select("*")\
            .eq("id", tile_id)\
            .eq("user_id", user_id)\
            .execute()

        if not res.data:
            logger.warning(f"⚠️  Tile ID={tile_id} not found or not owned by user {user_id[:8]}...")
            raise HTTPException(
                status_code=404,
                detail="Tile not found or not owned by user"
            )

        tile = res.data[0]
        logger.info(f"✅ Retrieved tile ID={tile_id} for user {user_id[:8]}...")

        return {
            "tile": tile
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error fetching tile: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch tile: {str(e)}"
        )


@router.patch("/api/tiles/{tile_id}", dependencies=[Depends(verify_token)])
async def update_tile(request: Request, tile_id: int, body: UpdateTileRequest):
    """
    Update a tile's details (name, size, price) by its ID.

    **Authentication Required:** Bearer token in Authorization header

    Args:
        request: FastAPI request (contains authenticated user_id)
        tile_id: ID of the tile to update
        body: Fields to update (only provided fields will be updated)

    Returns:
        JSON with success status and updated tile record

    Raises:
        HTTPException 400: If validation fails
        HTTPException 401: If authentication fails
        HTTPException 404: If tile not found or not owned by user
        HTTPException 422: If size exceeds 50 chars or price is negative
        HTTPException 500: If database operation fails
    """
    try:
        user_id = request.state.user_id
        logger.info(f"🔐 User {user_id[:8]}... updating tile ID={tile_id}")

        # Step 1: Verify tile exists and belongs to user
        existing = supabase.table("tiles")\
            .select("*")\
            .eq("id", tile_id)\
            .eq("user_id", user_id)\
            .execute()

        if not existing.data:
            logger.warning(f"⚠️  Tile ID={tile_id} not found or not owned by user {user_id[:8]}...")
            raise HTTPException(
                status_code=404,
                detail="Tile not found or not owned by user"
            )

        # Step 2: Build update payload with only provided fields
        update_data = {}
        if body.name is not None:
            update_data["name"] = body.name
        if body.size is not None:
            update_data["size"] = body.size
        if body.price is not None:
            update_data["price"] = body.price
        if body.add_catalog is not None:
            update_data["add_catalog"] = body.add_catalog

        # If no fields provided, return error
        if not update_data:
            raise HTTPException(
                status_code=400,
                detail="No fields provided to update"
            )

        # Step 3: Update tile record
        res = supabase.table("tiles")\
            .update(update_data)\
            .eq("id", tile_id)\
            .eq("user_id", user_id)\
            .execute()

        if not res.data:
            raise HTTPException(
                status_code=500,
                detail="Failed to update tile record"
            )

        tile = res.data[0]
        logger.info(f"✅ Tile ID={tile_id} updated for user {user_id[:8]}...")

        return {
            "success": True,
            "tile": tile
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error updating tile: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update tile: {str(e)}"
        )


@router.delete("/api/tiles/{tile_id}", dependencies=[Depends(verify_token)])
async def delete_tile(request: Request, tile_id: int):
    """
    Delete a tile by its ID (only if owned by the authenticated user).

    **Authentication Required:** Bearer token in Authorization header

    Args:
        request: FastAPI request (contains authenticated user_id)
        tile_id: ID of the tile to delete

    Returns:
        JSON with success status and deleted tile ID

    Raises:
        HTTPException 401: If authentication fails
        HTTPException 404: If tile not found or not owned by user
        HTTPException 500: If database operation fails
    """
    try:
        user_id = request.state.user_id
        logger.info(f"🔐 User {user_id[:8]}... attempting to delete tile ID={tile_id}")

        # Step 1: Verify tile exists and belongs to user
        existing = supabase.table("tiles")\
            .select("*")\
            .eq("id", tile_id)\
            .eq("user_id", user_id)\
            .execute()

        if not existing.data:
            logger.warning(f"⚠️  Tile ID={tile_id} not found or not owned by user {user_id[:8]}...")
            raise HTTPException(
                status_code=404,
                detail="Tile not found or not owned by user"
            )

        tile = existing.data[0]
        image_url = tile.get("image_url")

        # Step 2: Delete tile record from database
        supabase.table("tiles")\
            .delete()\
            .eq("id", tile_id)\
            .eq("user_id", user_id)\
            .execute()

        logger.info(f"✅ Tile ID={tile_id} deleted from database for user {user_id[:8]}...")

        # Step 3: Optional - Delete image file from Supabase Storage
        if image_url:
            try:
                # Extract bucket and filename from URL
                # URL format: https://.../storage/v1/object/public/{bucket}/{filename}
                url_parts = image_url.split("/")
                if "storage" in url_parts:
                    # Find bucket name (comes after 'public')
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
            "deleted_id": tile_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error deleting tile: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete tile: {str(e)}"
        )


@router.get("/api/tiles/{tile_id}/generated", dependencies=[Depends(verify_token)])
async def get_generated_images(request: Request, tile_id: int):
    """
    Get all generated images for a specific tile.

    **Authentication Required:** Bearer token in Authorization header

    Args:
        request: FastAPI request (contains authenticated user_id)
        tile_id: ID of the tile to get generated images for

    Returns:
        JSON with list of generated images with home info, ordered by created_at (newest first)

    Raises:
        HTTPException 401: If authentication fails
        HTTPException 500: If database operation fails
    """
    try:
        user_id = request.state.user_id
        logger.info(f"🔐 User {user_id[:8]}... fetching generated images for tile ID={tile_id}")

        # Query generated images for this tile and user
        # Include home info via join
        res = supabase.table("generated_images")\
            .select("*, homes(id, name, image_url)")\
            .eq("tile_id", tile_id)\
            .eq("user_id", user_id)\
            .order("created_at", desc=True)\
            .execute()

        generated = res.data if res.data else []
        logger.info(f"✅ Retrieved {len(generated)} generated images for tile ID={tile_id}, user {user_id[:8]}...")

        return {
            "generated": generated
        }

    except Exception as e:
        logger.error(f"❌ Error fetching generated images: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch generated images: {str(e)}"
        )
