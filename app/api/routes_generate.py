"""
Image generation endpoint.
"""
import os
import mimetypes
import httpx
import time
import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from supabase import create_client, Client
from app.services.prompt_builder import build_prompt

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


router = APIRouter()


# Pydantic request model for /generate endpoint
class GenerateRequest(BaseModel):
    """Request payload for /generate endpoint."""
    tile_url: str = Field(..., description="URL of the tile image")
    home_url: str = Field(..., description="URL of the home/room image")
    prompt: str = Field(
        default="",
        description="User hint or context (e.g., 'modern bathroom', 'kitchen backsplash')"
    )
    surface: str = Field(
        default="auto",
        description="Target surface: 'auto', 'floor', 'wall', 'backsplash', 'shower'"
    )


# Ensure generated folder exists
GENERATED_DIR = Path("generated")
GENERATED_DIR.mkdir(exist_ok=True)


@router.post("/generate")
async def generate_image(request: GenerateRequest):
    """
    Generate a visualization using Gemini 2.5 Flash Image API.

    This endpoint:
    1. Downloads both tile and home images from provided URLs
    2. Converts them to byte arrays
    3. Sends them + text prompt to Gemini 2.5 Flash Image API
    4. Receives generated image from the API
    5. Saves it locally to generated/ folder
    6. Uploads to Supabase Storage
    7. Inserts record into database
    8. Returns the public URL
    """
    try:
        # Step 1: Validate API key
        api_key = os.environ.get("NANO_BANANA_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="NANO_BANANA_API_KEY not configured on server"
            )

        # Initialize Supabase client
        supabase_url = os.environ.get("SUPABASE_URL")
        supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        bucket_name = os.environ.get("SUPABASE_STORAGE_BUCKET_GENERATED", "generated")

        if not supabase_url or not supabase_key:
            raise HTTPException(
                status_code=500,
                detail="Supabase credentials not configured on server"
            )

        supabase: Client = create_client(supabase_url, supabase_key)

        # Step 2: Download both images as byte arrays
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                # Download tile image
                tile_response = await client.get(request.tile_url)
                if tile_response.status_code != 200:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Failed to download tile image: HTTP {tile_response.status_code}"
                    )
                tile_bytes = tile_response.content

                # Download home image
                home_response = await client.get(request.home_url)
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
        user_hint = request.prompt if request.prompt else ""
        surface = request.surface if hasattr(request, 'surface') else "auto"

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

                # Save image to local disk first
                with open(local_path, "wb") as f:
                    f.write(data_buffer)

                logger.info(f"✅ Generated image saved locally: {local_path}")

                # Step 6: Upload to Supabase Storage
                try:
                    with open(local_path, "rb") as f:
                        supabase.storage.from_(bucket_name).upload(
                            file_name,
                            f,
                            file_options={"content-type": "image/jpeg"}
                        )
                    logger.info(f"✅ Uploaded to Supabase Storage: {file_name}")
                except Exception as upload_error:
                    logger.error(f"⚠️  Supabase upload error: {upload_error}")
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to upload to Supabase Storage: {str(upload_error)}"
                    )

                # Get public URL
                public_url = supabase.storage.from_(bucket_name).get_public_url(file_name)
                logger.info(f"✅ Public URL: {public_url}")

                # Step 7: Insert record into database
                try:
                    # Save user hint (not full AI prompt) for database record
                    user_prompt = request.prompt if request.prompt else "Auto-generated"
                    tile_id = None  # Will be None unless passed in request
                    user_id = None  # Will be None unless passed in request

                    db_record = {
                        "user_id": user_id,
                        "tile_id": tile_id,
                        "prompt": user_prompt,
                        "image_url": public_url,
                    }

                    result = supabase.table("generated_images").insert(db_record).execute()
                    logger.info(f"✅ Database record inserted: {result.data}")
                except Exception as db_error:
                    logger.error(f"⚠️  Database insert error: {db_error}")
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to insert database record: {str(db_error)}"
                    )

                # Step 8: Return success response with public URL
                return {
                    "success": True,
                    "image_url": public_url
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
