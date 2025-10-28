"""
Image generation endpoint.
"""
import os
import mimetypes
import httpx
import time
import logging
import aiofiles
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, Field
from typing import Optional
from google import genai
from google.genai import types
from app.services.prompt_builder import build_prompt
from app.services.auth import verify_token
from app.services.supabase_client import supabase

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


router = APIRouter()


# Pydantic request model for /generate endpoint
class GenerateRequest(BaseModel):
    """Request payload for /generate endpoint."""
    tile_url: Optional[str] = Field(None, description="URL of the tile image (provide either tile_url or tile_id)")
    home_url: Optional[str] = Field(None, description="URL of the home/room image (provide either home_url or home_id)")
    tile_id: Optional[int] = Field(None, description="ID of the tile from database (provide either tile_url or tile_id)")
    home_id: Optional[int] = Field(None, description="ID of the home from database (provide either home_url or home_id)")
    chat_id: Optional[int] = Field(None, description="ID of the chat session (optional)")
    prompt: str = Field(
        default="",
        description="User hint or context (e.g., 'modern bathroom', 'kitchen backsplash')"
    )
    surface: str = Field(
        default="auto",
        description="Target surface: 'auto', 'floor', 'wall', 'backsplash', 'shower'"
    )


# Pydantic request model for updating generated images
class UpdateGeneratedRequest(BaseModel):
    """Request payload for updating a generated image."""
    kept: Optional[bool] = Field(None, description="Flag to mark image as kept")
    tile_id: Optional[int] = Field(None, description="Link to a specific tile")


# Ensure generated folder exists
GENERATED_DIR = Path("generated")
GENERATED_DIR.mkdir(exist_ok=True)


@router.post("/generate", dependencies=[Depends(verify_token)])
async def generate_image(request: Request, body: GenerateRequest):
    """
    Generate a visualization using Gemini 2.5 Flash Image API.

    **Authentication Required:** Bearer token in Authorization header

    This endpoint accepts either URLs or IDs for tile and home images:
    - If tile_id/home_id provided: Fetches image URLs from database
    - If tile_url/home_url provided: Uses URLs directly
    - At least one source (ID or URL) must be provided for both tile and home

    Process:
    1. Validates input and fetches URLs from database if needed
    2. Downloads both tile and home images from URLs
    3. Converts them to byte arrays
    4. Sends them + text prompt to Gemini 2.5 Flash Image API
    5. Receives generated image from the API
    6. Saves it locally to generated/ folder
    7. Uploads to Supabase Storage
    8. Inserts record into database with chat_id if provided
    9. Returns the public URL
    """
    try:
        # Step 0: Extract authenticated user ID
        user_id = request.state.user_id
        logger.info(f"🔐 Authenticated user: {user_id[:8]}...")

        # Step 0.5: Validate tile and home sources
        # Check that we have either tile_url or tile_id
        if not body.tile_url and not body.tile_id:
            raise HTTPException(
                status_code=400,
                detail="Missing tile source: provide either tile_url or tile_id"
            )

        # Check that we have either home_url or home_id
        if not body.home_url and not body.home_id:
            raise HTTPException(
                status_code=400,
                detail="Missing home source: provide either home_url or home_id"
            )

        # Step 0.6: Fetch URLs from database if IDs provided but URLs missing
        tile_url = body.tile_url
        home_url = body.home_url

        if not tile_url and body.tile_id:
            logger.info(f"📥 Fetching tile URL from database for tile_id={body.tile_id}")
            tile_res = supabase.table("tiles")\
                .select("image_url")\
                .eq("id", body.tile_id)\
                .eq("user_id", user_id)\
                .execute()

            if not tile_res.data:
                raise HTTPException(
                    status_code=404,
                    detail=f"Tile with ID {body.tile_id} not found or not owned by user"
                )

            tile_url = tile_res.data[0]["image_url"]
            logger.info(f"✅ Fetched tile URL: {tile_url}")

        if not home_url and body.home_id:
            logger.info(f"📥 Fetching home URL from database for home_id={body.home_id}")
            home_res = supabase.table("homes")\
                .select("image_url")\
                .eq("id", body.home_id)\
                .eq("user_id", user_id)\
                .execute()

            if not home_res.data:
                raise HTTPException(
                    status_code=404,
                    detail=f"Home with ID {body.home_id} not found or not owned by user"
                )

            home_url = home_res.data[0]["image_url"]
            logger.info(f"✅ Fetched home URL: {home_url}")

        # Step 1: Validate API key
        api_key = os.environ.get("NANO_BANANA_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="NANO_BANANA_API_KEY not configured on server"
            )

        # Get bucket name for Supabase Storage
        bucket_name = os.environ.get("SUPABASE_STORAGE_BUCKET_GENERATED", "generated")

        # Step 2: Download both images as byte arrays
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                # Download tile image
                tile_response = await client.get(tile_url)
                if tile_response.status_code != 200:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Failed to download tile image: HTTP {tile_response.status_code}"
                    )
                tile_bytes = tile_response.content

                # Download home image
                home_response = await client.get(home_url)
                if home_response.status_code != 200:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Failed to download home image: HTTP {home_response.status_code}"
                    )
                home_bytes = home_response.content

            except httpx.TimeoutException:
                raise HTTPException(
                    status_code=400,
                    detail="Image download timed out"
                )
            except httpx.RequestError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to download images: {str(e)}"
                )

        # Step 3: Build intelligent prompt using prompt builder
        user_hint = body.prompt if body.prompt else ""
        surface = body.surface if hasattr(body, 'surface') else "auto"

        # Generate comprehensive prompt
        ai_prompt = build_prompt(user_hint=user_hint, surface=surface)

        # Log the generated prompt for debugging
        logger.info(f"🎨 Generated AI Prompt:\n{ai_prompt}")
        logger.info(f"📝 User hint: '{user_hint}'")
        logger.info(f"🎯 Surface: {surface}")

        # Step 4: Initialize Gemini client
        gemini_client = genai.Client(api_key=api_key)
        model = "gemini-2.5-flash-image"

        # Step 5: Build request content with explicit differentiation
        # The Parts list includes:
        # - AI-generated comprehensive prompt
        # - Clear labeling of TILE image
        # - Tile image data
        # - Clear labeling of HOUSE image
        # - House image data
        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=ai_prompt),
                    types.Part.from_text(text="The following image is the TILE design that should be applied:"),
                    types.Part(inline_data=types.Blob(mime_type="image/jpeg", data=tile_bytes)),
                    types.Part.from_text(text="The following image is the HOUSE/ROOM where the tile should be installed:"),
                    types.Part(inline_data=types.Blob(mime_type="image/jpeg", data=home_bytes)),
                ],
            ),
        ]

        logger.info("📤 Sending request to Gemini API with differentiated images")

        # Configure to return image output
        config = types.GenerateContentConfig(
            response_modalities=["IMAGE"]
        )

        # Step 5: Call Gemini API and stream response
        file_index = 0
        image_saved = False

        for chunk in gemini_client.models.generate_content_stream(
            model=model,
            contents=contents,
            config=config,
        ):
            # Check if chunk contains valid image data
            if (
                not chunk.candidates
                or not chunk.candidates[0].content
                or not chunk.candidates[0].content.parts
            ):
                continue

            part = chunk.candidates[0].content.parts[0]

            # Extract inline image data if present
            if getattr(part, "inline_data", None) and part.inline_data.data:
                inline_data = part.inline_data
                data_buffer = inline_data.data

                # Determine file extension from MIME type
                file_extension = mimetypes.guess_extension(inline_data.mime_type)
                if not file_extension:
                    file_extension = ".jpg"  # Default to .jpg

                # Generate timestamp-based filename for uniqueness
                file_name = f"generated_output_{int(time.time())}.jpg"
                local_path = GENERATED_DIR / file_name

                # Save image to local disk first (async for better performance)
                async with aiofiles.open(local_path, "wb") as f:
                    await f.write(data_buffer)

                logger.info(f"✅ Generated image saved locally: {local_path}")

                # Step 6: Upload to Supabase Storage
                try:
                    async with aiofiles.open(local_path, "rb") as f:
                        file_data = await f.read()
                        supabase.storage.from_(bucket_name).upload(
                            file_name,
                            file_data,
                            file_options={"content-type": "image/jpeg"}
                        )
                    logger.info(f"✅ Uploaded to Supabase Storage: {file_name}")
                except Exception as upload_error:
                    logger.error(f"⚠️  Supabase upload error: {upload_error}")
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to upload to Supabase Storage: {str(upload_error)}"
                    )

                # Get optimized public URL with CDN caching and compression
                SUPABASE_URL = os.getenv("SUPABASE_URL")
                public_url = f"{SUPABASE_URL}/storage/v1/render/image/public/{bucket_name}/{file_name}?width=512&quality=80"
                logger.info(f"✅ Public URL: {public_url}")

                # Step 7: Insert record into database with authenticated user_id
                try:
                    # Save user hint (not full AI prompt) for database record
                    user_prompt = body.prompt if body.prompt else "Auto-generated"

                    # Note: tile_id is intentionally NOT included here
                    # Generated images remain unlinked until user explicitly adds reference via PATCH endpoint
                    db_record = {
                        "user_id": user_id,  # Authenticated user from JWT
                        "home_id": body.home_id,  # Home ID from request (optional)
                        "chat_id": body.chat_id,  # Chat ID from request (optional)
                        "prompt": user_prompt,
                        "image_url": public_url,
                    }

                    result = supabase.table("generated_images").insert(db_record).execute()
                    logger.info(f"✅ Database record inserted for user {user_id[:8]}... (home_id={body.home_id}, chat_id={body.chat_id}, tile_id=NULL): {result.data}")

                    # Get the inserted record with all fields
                    if not result.data:
                        raise HTTPException(
                            status_code=500,
                            detail="Failed to retrieve inserted record"
                        )

                    inserted_record = result.data[0]

                except Exception as db_error:
                    logger.error(f"⚠️  Database insert error: {db_error}")
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to insert database record: {str(db_error)}"
                    )

                # Step 8: Return success response with full image record
                return {
                    "success": True,
                    "image": inserted_record
                }

        # If we get here, no image was returned
        raise HTTPException(
            status_code=500,
            detail="No image parts returned from Gemini API"
        )

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise

    except Exception as e:
        # Catch-all for unexpected errors
        import traceback
        logger.error(f"❌ Error in /generate: {str(e)}")
        logger.error(traceback.format_exc())

        raise HTTPException(
            status_code=500,
            detail=f"Image generation failed: {str(e)}"
        )


@router.patch("/api/generated/{image_id}", dependencies=[Depends(verify_token)])
async def update_generated_image(request: Request, image_id: int, body: UpdateGeneratedRequest):
    """
    Update a generated image's kept flag or tile link.

    **Authentication Required:** Bearer token in Authorization header

    Args:
        request: FastAPI request (contains authenticated user_id)
        image_id: ID of the generated image to update
        body: Fields to update (kept flag or tile_id)

    Returns:
        JSON with success status and updated image record

    Raises:
        HTTPException 400: If no fields provided or validation fails
        HTTPException 401: If authentication fails
        HTTPException 404: If image not found or not owned by user
        HTTPException 500: If database operation fails
    """
    try:
        user_id = request.state.user_id
        logger.info(f"🔐 User {user_id[:8]}... updating generated image ID={image_id}")

        # Step 1: Verify image exists and belongs to user
        existing = supabase.table("generated_images")\
            .select("*")\
            .eq("id", image_id)\
            .eq("user_id", user_id)\
            .execute()

        if not existing.data:
            logger.warning(f"⚠️  Generated image ID={image_id} not found or not owned by user {user_id[:8]}...")
            raise HTTPException(
                status_code=404,
                detail="Generated image not found or not owned by user"
            )

        # Step 2: Build update payload with only provided fields
        update_data = {}
        if body.kept is not None:
            update_data["kept"] = body.kept
        if body.tile_id is not None:
            update_data["tile_id"] = body.tile_id

        # If no fields provided, return error
        if not update_data:
            raise HTTPException(
                status_code=400,
                detail="No fields provided to update"
            )

        # Step 3: Update generated image record
        res = supabase.table("generated_images")\
            .update(update_data)\
            .eq("id", image_id)\
            .eq("user_id", user_id)\
            .execute()

        if not res.data:
            raise HTTPException(
                status_code=500,
                detail="Failed to update generated image record"
            )

        image = res.data[0]
        logger.info(f"✅ Generated image ID={image_id} updated for user {user_id[:8]}...")

        return {
            "success": True,
            "image": image
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error updating generated image: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update generated image: {str(e)}"
        )


@router.delete("/api/generated/{image_id}", dependencies=[Depends(verify_token)])
async def delete_generated_image(request: Request, image_id: int):
    """
    Delete a generated image (and optionally its file from Supabase storage).

    **Authentication Required:** Bearer token in Authorization header

    Args:
        request: FastAPI request (contains authenticated user_id)
        image_id: ID of the generated image to delete

    Returns:
        JSON with success status and deleted image ID

    Raises:
        HTTPException 401: If authentication fails
        HTTPException 404: If image not found or not owned by user
        HTTPException 500: If database operation fails
    """
    try:
        user_id = request.state.user_id
        logger.info(f"🔐 User {user_id[:8]}... attempting to delete generated image ID={image_id}")

        bucket_name = os.environ.get("SUPABASE_STORAGE_BUCKET_GENERATED", "generated")

        # Step 1: Verify image exists and belongs to user
        existing = supabase.table("generated_images")\
            .select("*")\
            .eq("id", image_id)\
            .eq("user_id", user_id)\
            .execute()

        if not existing.data:
            logger.warning(f"⚠️  Generated image ID={image_id} not found or not owned by user {user_id[:8]}...")
            raise HTTPException(
                status_code=404,
                detail="Generated image not found or not owned by user"
            )

        image = existing.data[0]
        image_url = image.get("image_url")

        # Step 2: Delete image record from database
        supabase.table("generated_images")\
            .delete()\
            .eq("id", image_id)\
            .eq("user_id", user_id)\
            .execute()

        logger.info(f"✅ Generated image ID={image_id} deleted from database for user {user_id[:8]}...")

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
            "deleted_id": image_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error deleting generated image: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete generated image: {str(e)}"
        )


@router.get("/test-gemini")
async def test_gemini():
    try:
        # Check if API key exists
        api_key = os.environ.get("NANO_BANANA_API_KEY")
        if not api_key:
            return {
                "success": False,
                "error": "NANO_BANANA_API_KEY not found in environment variables",
                "debug": f"Available env vars: {list(os.environ.keys())}"
            }

        # Show key length for debugging (don't show actual key)
        print(f"API Key loaded: {len(api_key)} characters")

        client = genai.Client(api_key=api_key)
        model = "gemini-2.5-flash-image"

        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text="Generate a photo of a wall with white ceramic tiles and good lighting."),
                ],
            ),
        ]

        config = types.GenerateContentConfig(
            response_modalities=["IMAGE"]
        )

        file_index = 0
        for chunk in client.models.generate_content_stream(
            model=model,
            contents=contents,
            config=config,
        ):
            if (
                not chunk.candidates
                or not chunk.candidates[0].content
                or not chunk.candidates[0].content.parts
            ):
                continue
            part = chunk.candidates[0].content.parts[0]
            if getattr(part, "inline_data", None) and part.inline_data.data:
                file_name = f"test_output_{file_index}"
                file_index += 1
                inline_data = part.inline_data
                data_buffer = inline_data.data
                file_extension = mimetypes.guess_extension(inline_data.mime_type)
                with open(f"{file_name}{file_extension}", "wb") as f:
                    f.write(data_buffer)
                return {"success": True, "message": f"Saved as {file_name}{file_extension}"}

        return {"success": False, "error": "No image parts received"}

    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }
