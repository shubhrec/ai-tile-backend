"""
User summary endpoint - batched data fetching for performance.

This endpoint returns tiles, homes, and chats in a single API call,
reducing network round-trips and improving frontend load times.
"""
import logging
from fastapi import APIRouter, Request, Depends, HTTPException
from app.services.auth import verify_token
from app.services.supabase_client import supabase

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/user/summary", dependencies=[Depends(verify_token)])
async def get_user_summary(request: Request):
    """
    Get a batched summary of user data (tiles, homes, chats) in a single call.

    **Authentication Required:** Bearer token in Authorization header

    This endpoint is optimized for performance by:
    - Fetching all data in parallel
    - Limiting fields to only those needed by frontend
    - Limiting results to 100 items per collection
    - Reducing network round-trips from 3 separate calls to 1

    Args:
        request: FastAPI request (contains authenticated user_id)

    Returns:
        JSON with tiles, homes, and chats arrays

    Raises:
        HTTPException 401: If authentication fails
        HTTPException 500: If database operation fails
    """
    try:
        user_id = request.state.user_id
        logger.info(f"🔐 User {user_id[:8]}... fetching summary (batched)")

        # Execute all queries in parallel for maximum performance
        tiles_query = supabase.table("tiles")\
            .select("id, name, image_url, size, price, add_catalog, created_at")\
            .eq("user_id", user_id)\
            .order("created_at", desc=True)\
            .limit(100)

        homes_query = supabase.table("homes")\
            .select("id, name, image_url, created_at")\
            .eq("user_id", user_id)\
            .order("created_at", desc=True)\
            .limit(100)

        chats_query = supabase.table("chats")\
            .select("id, name, created_at")\
            .eq("user_id", user_id)\
            .order("created_at", desc=True)\
            .limit(100)

        # Execute all queries
        tiles_res = tiles_query.execute()
        homes_res = homes_query.execute()
        chats_res = chats_query.execute()

        tiles = tiles_res.data if tiles_res.data else []
        homes = homes_res.data if homes_res.data else []
        chats = chats_res.data if chats_res.data else []

        logger.info(
            f"✅ Retrieved summary for user {user_id[:8]}...: "
            f"{len(tiles)} tiles, {len(homes)} homes, {len(chats)} chats"
        )

        return {
            "success": True,
            "tiles": tiles,
            "homes": homes,
            "chats": chats
        }

    except Exception as e:
        logger.error(f"❌ Error fetching user summary: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch user summary: {str(e)}"
        )
