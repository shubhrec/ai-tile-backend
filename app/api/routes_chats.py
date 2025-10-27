"""
Chat-based generation endpoints.

Endpoints for managing chat sessions and their associated generated images.
Each chat represents a conversation thread where multiple tile visualizations
can be generated and managed.
"""
import logging
from datetime import datetime
from fastapi import APIRouter, Request, Depends, HTTPException
from app.services.auth import verify_token
from app.services.supabase_client import supabase

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/chats", dependencies=[Depends(verify_token)])
async def create_chat(request: Request):
    """
    Create a new chat session for the authenticated user.

    **Authentication Required:** Bearer token in Authorization header

    Args:
        request: FastAPI request (contains authenticated user_id)

    Returns:
        JSON with success status and created chat record

    Raises:
        HTTPException 401: If authentication fails
        HTTPException 500: If database operation fails
    """
    try:
        user_id = request.state.user_id
        logger.info(f"🔐 User {user_id[:8]}... creating new chat")

        # Generate chat name with current date/time
        chat_name = f"Customer Chat - {datetime.now().strftime('%b %d, %Y %I:%M %p')}"

        # Insert chat record
        res = supabase.table("chats").insert({
            "user_id": user_id,
            "name": chat_name,
        }).execute()

        if not res.data:
            raise HTTPException(
                status_code=500,
                detail="Failed to create chat record"
            )

        chat = res.data[0]
        logger.info(f"✅ Chat created: ID={chat.get('id')} for user {user_id[:8]}...")

        return {
            "success": True,
            "chat": chat
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error creating chat: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create chat: {str(e)}"
        )


@router.get("/api/chats", dependencies=[Depends(verify_token)])
async def get_chats(request: Request):
    """
    Get all chat sessions for the authenticated user.

    **Authentication Required:** Bearer token in Authorization header

    Args:
        request: FastAPI request (contains authenticated user_id)

    Returns:
        JSON with list of user's chats, ordered by created_at (newest first)

    Raises:
        HTTPException 401: If authentication fails
        HTTPException 500: If database operation fails
    """
    try:
        user_id = request.state.user_id
        logger.info(f"🔐 User {user_id[:8]}... fetching chats")

        # Query chats for this user (limit results for performance)
        res = supabase.table("chats")\
            .select("id, name, created_at")\
            .eq("user_id", user_id)\
            .order("created_at", desc=True)\
            .limit(100)\
            .execute()

        chats = res.data if res.data else []
        logger.info(f"✅ Retrieved {len(chats)} chats for user {user_id[:8]}...")

        return {
            "success": True,
            "chats": chats
        }

    except Exception as e:
        logger.error(f"❌ Error fetching chats: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch chats: {str(e)}"
        )


@router.get("/api/chats/{chat_id}", dependencies=[Depends(verify_token)])
async def get_chat_with_images(request: Request, chat_id: int):
    """
    Get a single chat session with its associated generated images.

    **Authentication Required:** Bearer token in Authorization header

    Args:
        request: FastAPI request (contains authenticated user_id)
        chat_id: ID of the chat to retrieve

    Returns:
        JSON with chat data and array of generated images

    Raises:
        HTTPException 401: If authentication fails
        HTTPException 404: If chat not found or not owned by user
        HTTPException 500: If database operation fails
    """
    try:
        user_id = request.state.user_id
        logger.info(f"🔐 User {user_id[:8]}... fetching chat ID={chat_id}")

        # Step 1: Fetch chat record
        chat_res = supabase.table("chats")\
            .select("*")\
            .eq("id", chat_id)\
            .eq("user_id", user_id)\
            .execute()

        if not chat_res.data:
            logger.warning(f"⚠️  Chat ID={chat_id} not found or not owned by user {user_id[:8]}...")
            raise HTTPException(
                status_code=404,
                detail="Chat not found or not owned by user"
            )

        chat = chat_res.data[0]

        # Step 2: Fetch associated generated images with tile names (limit results for performance)
        images_res = supabase.table("generated_images")\
            .select("id, chat_id, image_url, prompt, kept, tile_id, home_id, created_at, tiles(name)")\
            .eq("chat_id", chat_id)\
            .eq("user_id", user_id)\
            .order("created_at", desc=True)\
            .limit(100)\
            .execute()

        images = images_res.data if images_res.data else []

        # Flatten the nested tile name for easier frontend access
        for img in images:
            if "tiles" in img and img["tiles"]:
                img["tile_name"] = img["tiles"]["name"]
                del img["tiles"]  # Remove nested object to keep response clean
            else:
                img["tile_name"] = None

        logger.info(f"✅ Retrieved chat ID={chat_id} with {len(images)} images for user {user_id[:8]}...")

        return {
            "chat": chat,
            "images": images
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error fetching chat: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch chat: {str(e)}"
        )
