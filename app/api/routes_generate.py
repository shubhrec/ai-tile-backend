"""
Image generation endpoint.
"""
import os
import mimetypes
import httpx
import time
import logging
import aiofiles
import json
import re
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, Field
from typing import Optional
from google import genai
from google.genai import types
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
    home_url: Optional[str] = Field(None, description="URL of the home/room image (provide either home_url, home_id, or base_image_url)")
    tile_id: Optional[int] = Field(None, description="ID of the tile from database (provide either tile_url or tile_id)")
    home_id: Optional[int] = Field(None, description="ID of the home from database (provide either home_url, home_id, or base_image_url)")
    base_image_url: Optional[str] = Field(None, description="URL of a previously generated image to use as base for multi-stage generation")
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

    This endpoint supports two generation modes:

    1. **Standard Generation**: Apply tiles to a new room/home image
       - If tile_id/home_id provided: Fetches image URLs from database
       - If tile_url/home_url provided: Uses URLs directly
       - At least one source (ID or URL) must be provided for both tile and home

    2. **Multi-Stage Generation**: Apply new tiles to a previously generated image
       - Provide base_image_url: URL of a previously generated image
       - The new tile will be applied to a different surface
       - Preserves existing tile work and applies new tile to complementary surfaces

    Process:
    1. Validates input and fetches URLs from database if needed
    2. Downloads both tile and base images (home or previous generation) from URLs
    3. Converts them to byte arrays
    4. Builds appropriate prompt (continuation or standard) based on input
    5. Sends images + text prompt to Gemini 2.5 Flash Image API
    6. Receives generated image from the API
    7. Saves it locally to generated/ folder
    8. Uploads to Supabase Storage
    9. Inserts record into database with chat_id if provided
    10. Returns the public URL
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

        # Check that we have either home_url, home_id, or base_image_url
        if not body.home_url and not body.home_id and not body.base_image_url:
            raise HTTPException(
                status_code=400,
                detail="Missing base image source: provide either home_url, home_id, or base_image_url"
            )

        # Step 0.6: Fetch URLs from database if IDs provided but URLs missing
        tile_url = body.tile_url
        home_url = body.home_url
        base_image_url = body.base_image_url
        is_multi_stage = bool(base_image_url)

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

        # Determine which base image to use: base_image_url takes precedence over home_url/home_id
        if base_image_url:
            home_url = base_image_url
            logger.info(f"✅ Multi-stage generation: Using base_image_url as primary image")
            logger.info(f"   Base image URL: {base_image_url[:80]}...")
        elif not home_url and body.home_id:
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

        # Step 3: Initialize Gemini client and helper functions
        gemini_client = genai.Client(api_key=api_key)
        model = "gemini-2.5-flash-image"

        # Helper function for retry logic with exponential backoff
        def call_gemini_with_retry(contents, config, max_retries=3, timeout=120):
            """Call Gemini with automatic retry logic and timeout handling."""
            import asyncio
            from asyncio import TimeoutError as AsyncTimeoutError

            for attempt in range(max_retries):
                try:
                    logger.info(f"🔄 Attempt {attempt + 1}/{max_retries}...")

                    # Call Gemini with timeout
                    response = gemini_client.models.generate_content(
                        model=model,
                        contents=contents,
                        config=config,
                    )

                    if not response:
                        raise ValueError("Empty response from Gemini")

                    logger.info(f"✅ Gemini call successful on attempt {attempt + 1}")
                    return response

                except Exception as e:
                    logger.warning(f"⚠️ Attempt {attempt + 1} failed: {str(e)}")

                    if attempt == max_retries - 1:
                        # Last attempt failed
                        raise

                    # Wait before retry with exponential backoff
                    wait_time = (2 ** attempt) * 2  # 2s, 4s, 8s
                    logger.info(f"⏳ Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)

            raise Exception("Max retries exceeded")

        # Step 4: PASS 1 - Context Understanding with robust error handling
        logger.info("🔍 Pass 1: Analyzing images for context understanding...")

        context = {
            "surface_type": "floor",
            "estimated_tile_size": "medium",
            "region_description": "bottom part of the image",
            "lighting_condition": "natural"
        }

        try:
            context_prompt = """Analyze the two provided images and extract context.

TILE IMAGE Analysis:
- Determine if tile is for floors, walls, or backsplash
- Estimate size (small <300mm, medium 300-600mm, large >600mm)
- Identify material type (ceramic, marble, wood, stone, etc.)
- Note if glossy or matte finish

HOUSE IMAGE Analysis:
- Identify the room type and existing lighting
- Determine which surface(s) should receive the tile
- Note the lighting condition (bright/natural/dim/artificial)

Output ONLY a JSON object:
{
  "surface_type": "floor|wall|backsplash",
  "estimated_tile_size": "small|medium|large",
  "region_description": "descriptive location",
  "lighting_condition": "lighting type"
}"""

            context_contents = [
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(text=context_prompt),
                        types.Part.from_text(text="TILE IMAGE:"),
                        types.Part(inline_data=types.Blob(mime_type="image/jpeg", data=tile_bytes)),
                        types.Part.from_text(text="HOUSE/ROOM IMAGE:"),
                        types.Part(inline_data=types.Blob(mime_type="image/jpeg", data=home_bytes)),
                    ],
                ),
            ]

            context_config = types.GenerateContentConfig(
                response_modalities=["TEXT"]
            )

            # Call with retry logic
            context_response = call_gemini_with_retry(context_contents, context_config, max_retries=2, timeout=60)

            # Parse response safely
            context_text = context_response.text if hasattr(context_response, 'text') else ""

            if not context_text or len(context_text.strip()) == 0:
                raise ValueError("Empty context response")

            logger.info(f"🔍 Context analysis response:\n{context_text[:500]}...")

            # Extract JSON with multiple fallback patterns
            json_match = re.search(r'\{[^}]+\}', context_text, re.DOTALL)
            if json_match:
                parsed_context = json.loads(json_match.group(0))

                # Validate required fields
                if all(key in parsed_context for key in ["surface_type", "region_description"]):
                    context.update(parsed_context)
                    logger.info(f"✅ Parsed context: {context}")
                else:
                    logger.warning("⚠️ Incomplete context JSON, using defaults")
            else:
                logger.warning("⚠️ No JSON found in context response, using defaults")

        except Exception as e:
            logger.warning(f"⚠️ Context analysis failed: {str(e)}. Using default context.")

        # Step 5: PASS 2 - Final Generation with improved prompt
        logger.info("🎨 Pass 2: Generating final visualization with robust prompt...")

        user_prompt = body.prompt if body.prompt else ""

        # Build comprehensive, bulletproof generation prompt
        # Use different prompt for multi-stage generation
        if is_multi_stage:
            # Multi-stage continuation prompt
            tile_name = "provided tile image"
            generation_prompt = f"""You are performing a *continuation* visualization task for marketing and sales.
The base image already contains previous tile renderings on some surfaces.

IMPORTANT CONTEXT:
This visualization is for SELLING TILES. The output must be attractive, clean, and professionally styled to showcase BOTH the existing and new tiles in the best possible light.

CRITICAL CONTEXT:
- The base image you're working with already has tiles applied to certain surfaces (may be interior or exterior)
- Your task is to apply a NEW tile to a DIFFERENT surface
- DO NOT modify or alter any previously tiled areas
- This is a continuation of a professional tile showcase

INSTRUCTIONS:

Step 1: PRESERVE & ENHANCE EXISTING WORK
- Keep all existing tiled surfaces EXACTLY the same
- Identify which surfaces already have tiles applied
- DO NOT modify previously tiled areas under any circumstances
- Maintain all existing shadows, reflections, and lighting conditions
- If there are any minor imperfections in the base image (clutter not related to tiles), subtly clean them up while preserving all tile work
- Keep the professional, magazine-worthy aesthetic

Step 2: IDENTIFY NEW SURFACE
- Identify a *new logical surface* (e.g., wall, counter, backsplash, exterior wall, facade, etc.) to apply the new tile
- Choose a surface that is DIFFERENT from surfaces that already have tiles
- Common progressions:
  * Interior: floor → wall → backsplash → countertop
  * Exterior: patio/walkway → exterior walls → facade → outdoor features
- IMPORTANT: For exterior spaces, consider applying tiles to outer walls, building facades, or outdoor surfaces
- Ensure the chosen surface makes architectural sense and enhances the overall visualization

Step 3: APPLY NEW TILE
- Apply the new tile ({tile_name}) only on the specified NEW surface
- Surface type guidance: {context.get('surface_type', 'auto')}
- Tile size appears: {context.get('estimated_tile_size', 'medium')}
- Keep tile color and texture IDENTICAL to the new tile image provided
- Maintain correct perspective and alignment with the room/building geometry
- For exterior applications: Ensure tiles look weather-appropriate and structurally sound
- Make the new tile application look professional and aspirational

Step 4: MAINTAIN REALISM
- Preserve reflections and shadows from the base image
- Adjust perspective naturally for the new surface
- Match color tones and lighting between old and new surfaces
- Avoid any blending artifacts or duplicate tiles
- Ensure seamless integration with existing tiled surfaces
- Maintain consistent, bright, appealing lighting across all surfaces
- Create a cohesive, professional look

Step 5: QUALITY REQUIREMENTS
- Output must look like a single, cohesive professional architectural photograph
- Magazine-worthy quality that makes customers want to buy these tiles
- No visible seams between old and new tile applications
- Both old and new tiles should be clearly visible and beautifully showcased in the final output
- Preserve the exact appearance of previously applied tiles
- Same lighting and color grading throughout the image
- Professional staging and styling throughout

CRITICAL RULES:
❌ Do NOT modify previously tiled areas
❌ Do NOT change existing lighting or shadows dramatically
❌ Do NOT add tiles to surfaces that already have tiles
❌ Do NOT create duplicate or overlapping tile patterns
❌ Do NOT ignore exterior walls - continuation can include outer walls when appropriate
❌ Do NOT leave clutter or mess visible

✅ DO keep existing tile work exactly as is
✅ DO apply new tile to a different, logical surface (interior OR exterior)
✅ DO maintain physical realism and perspective
✅ DO ensure both old and new tiles are visible and beautifully showcased
✅ DO create a professional, aspirational visualization
✅ DO apply tiles to exterior walls, facades, or outdoor surfaces when contextually appropriate"""

            if user_prompt and user_prompt.strip():
                generation_prompt += f"\n\n🎯 USER REQUEST (highest priority): '{user_prompt.strip()}'"

            logger.info(f"✅ Multi-stage generation: Used base_image_url + new tile")
        else:
            # Standard first-generation prompt
            generation_prompt = f"""You are an expert visual compositor creating a photorealistic tile visualization for marketing and sales.

TASK:
You have two images:
1. A house or room photo (base image) - may be interior or exterior
2. A tile sample (to be applied)

IMPORTANT CONTEXT:
This visualization is for SELLING TILES. The output must be attractive, clean, and professionally styled to showcase the tiles in the best possible light.

INSTRUCTIONS:
Step 1: IMAGE ENHANCEMENT & CLEANUP
- If the base image has clutter, mess, or unattractive elements, CLEAN THEM UP
- Remove or minimize: scattered objects, clutter, dirt, stains, damage, poor styling
- Enhance the space to look professionally staged and magazine-worthy
- Maintain the architectural structure but improve the aesthetics
- Make the scene bright, inviting, and appealing to potential customers
- The goal is to create an aspirational visualization that sells tiles

Step 2: REGION IDENTIFICATION
- Apply tiles to: {context.get('region_description', 'the appropriate floor or wall area')}
- Surface type: {context.get('surface_type', 'floor')}
- IMPORTANT: If this is an exterior photo (house facade, outdoor patio, etc.), apply tiles to EXTERIOR WALLS, outdoor floors, or facades as appropriate
- For INTERIOR spaces: Apply to floors, walls, backsplashes, or shower areas as appropriate
- For EXTERIOR spaces: Apply to outer walls, facades, patios, walkways, or outdoor surfaces
- Use context clues (furniture position, room layout, architectural features) to infer correct boundaries
- Never place tiles where they wouldn't naturally appear

Step 3: PHYSICAL REALISM
- Maintain perfect perspective alignment with room/building geometry
- Preserve enhanced lighting ({context.get('lighting_condition', 'natural ambient')}) - make it bright and appealing
- Keep all shadows, reflections, and ambient occlusion realistic but polished
- Respect object boundaries (furniture, fixtures, people, architectural elements) — do not tile over them
- For exterior applications: Consider weatherproofing, outdoor lighting, and natural context

Step 4: TILE APPLICATION
- Tile size appears: {context.get('estimated_tile_size', 'medium')}
- Maintain correct aspect ratio and pattern alignment
- Ensure realistic grout lines with consistent spacing
- Keep tile color and texture IDENTICAL to the tile image
- If tile is glossy, reflect ambient light naturally to enhance visual appeal
- If tile has pattern, maintain continuity without warping
- For exterior walls: Ensure tiles look weather-appropriate and structurally sound

Step 5: QUALITY REQUIREMENTS
- Output must look like a professional architectural photograph from a design magazine
- Create an aspirational, beautiful space that makes customers want to buy these tiles
- No distortion, duplication, or pattern breaks
- Soft blending at tile boundaries for seamless integration
- Enhanced wall colors and textures to complement the tiles
- Professional staging and styling throughout
- Bright, attractive lighting that showcases the tiles beautifully

CRITICAL RULES:
❌ Do NOT tile over: ceilings, doors, windows, furniture, decorative elements, people
❌ Do NOT add extra reflections or tiles outside intended regions
❌ Do NOT leave clutter or mess visible - clean up the space
❌ Do NOT warp or stretch the tile pattern
❌ Do NOT ignore exterior walls - tiles can and should be applied to outer walls when appropriate

✅ DO maintain physical realism and perspective
✅ DO clean up and enhance the base image for marketing appeal
✅ DO apply tiles to exterior walls, facades, and outdoor surfaces when contextually appropriate
✅ DO create an attractive, magazine-worthy visualization
✅ DO ensure color fidelity to original tile image
✅ DO make the space look professionally staged and inviting"""

            if user_prompt and user_prompt.strip():
                generation_prompt += f"\n\n🎯 USER REQUEST (highest priority): {user_prompt.strip()}"

        logger.info(f"🎨 Using generation prompt (length: {len(generation_prompt)} chars)")

        # Build generation content
        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=generation_prompt),
                    types.Part.from_text(text="TILE IMAGE (to apply):"),
                    types.Part(inline_data=types.Blob(mime_type="image/jpeg", data=tile_bytes)),
                    types.Part.from_text(text="HOUSE/ROOM IMAGE (base):"),
                    types.Part(inline_data=types.Blob(mime_type="image/jpeg", data=home_bytes)),
                ],
            ),
        ]

        config = types.GenerateContentConfig(
            response_modalities=["IMAGE"]
        )

        # Step 6: Call Gemini API with retry logic and fallback
        image_saved = False
        data_buffer = None
        generation_attempts = 0
        max_generation_attempts = 2

        while not image_saved and generation_attempts < max_generation_attempts:
            generation_attempts += 1

            try:
                logger.info(f"🎨 Image generation attempt {generation_attempts}/{max_generation_attempts}...")

                # Try complex prompt first, then fallback to simplified
                if generation_attempts == 2:
                    logger.warning("⚠️ Falling back to simplified prompt...")
                    simplified_prompt = f"""Replace only the visible {context.get('surface_type', 'floor')} area with the tile texture.
Keep everything else (walls, objects, lighting) identical to the original photo.
Ensure tiles are evenly spaced and maintain their original color."""

                    if user_prompt and user_prompt.strip():
                        simplified_prompt += f"\nUser note: {user_prompt.strip()}"

                    # Rebuild with simplified prompt
                    contents = [
                        types.Content(
                            role="user",
                            parts=[
                                types.Part.from_text(text=simplified_prompt),
                                types.Part.from_text(text="TILE:"),
                                types.Part(inline_data=types.Blob(mime_type="image/jpeg", data=tile_bytes)),
                                types.Part.from_text(text="ROOM:"),
                                types.Part(inline_data=types.Blob(mime_type="image/jpeg", data=home_bytes)),
                            ],
                        ),
                    ]

                # Stream response with timeout handling
                chunk_count = 0
                for chunk in gemini_client.models.generate_content_stream(
                    model=model,
                    contents=contents,
                    config=config,
                ):
                    chunk_count += 1

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

                        if not data_buffer or len(data_buffer) == 0:
                            raise ValueError("Empty image data received")

                        logger.info(f"✅ Image data received (size: {len(data_buffer)} bytes)")

                        # Generate timestamp-based filename for uniqueness
                        file_name = f"generated_output_{int(time.time())}.jpg"
                        local_path = GENERATED_DIR / file_name

                        # Save image to local disk first (async for better performance)
                        async with aiofiles.open(local_path, "wb") as f:
                            await f.write(data_buffer)

                        image_saved = True
                        logger.info(f"✅ Generated image saved locally: {local_path}")
                        break  # Exit chunk loop

                if not image_saved:
                    raise ValueError(f"No image data received after {chunk_count} chunks")

                # If we got here, image was saved successfully
                break  # Exit retry loop

            except Exception as e:
                logger.error(f"❌ Generation attempt {generation_attempts} failed: {str(e)}")

                if generation_attempts >= max_generation_attempts:
                    # All attempts failed, return error
                    logger.error("❌ All generation attempts exhausted")
                    return {
                        "success": False,
                        "error": "Image generation failed. The AI model could not produce a valid visualization. Please try again with different images or contact support."
                    }

                # Wait before next attempt
                time.sleep(3)

        # Verify we have image data before continuing
        if not image_saved or not data_buffer:
            logger.error("❌ No image data available after all attempts")
            return {
                "success": False,
                "error": "Image generation failed to produce output. Please try again."
            }

        # Step 7: Upload to Supabase Storage with error handling
        try:
            logger.info(f"📤 Uploading to Supabase Storage: {file_name}")
            async with aiofiles.open(local_path, "rb") as f:
                file_data = await f.read()
                supabase.storage.from_(bucket_name).upload(
                    file_name,
                    file_data,
                    file_options={"content-type": "image/jpeg"}
                )
            logger.info(f"✅ Uploaded to Supabase Storage: {file_name}")
        except Exception as upload_error:
            logger.error(f"❌ Supabase upload error: {upload_error}")
            return {
                "success": False,
                "error": f"Image generated successfully but failed to upload to storage: {str(upload_error)}"
            }

        # Get public URL
        try:
            public_url = supabase.storage.from_(bucket_name).get_public_url(file_name)
            logger.info(f"✅ Public URL: {public_url}")
        except Exception as url_error:
            logger.error(f"❌ Failed to get public URL: {url_error}")
            return {
                "success": False,
                "error": "Image uploaded but failed to generate public URL. Please contact support."
            }

        # Step 8: Insert record into database with authenticated user_id
        try:
            # Save user hint (not full AI prompt) for database record
            user_prompt_text = body.prompt if body.prompt else "Auto-generated"

            # Note: tile_id is intentionally NOT included here
            # Generated images remain unlinked until user explicitly adds reference via PATCH endpoint
            db_record = {
                "user_id": user_id,  # Authenticated user from JWT
                "home_id": body.home_id,  # Home ID from request (optional)
                "chat_id": body.chat_id,  # Chat ID from request (optional)
                "prompt": user_prompt_text,
                "image_url": public_url,
            }

            result = supabase.table("generated_images").insert(db_record).execute()
            logger.info(f"✅ Database record inserted for user {user_id[:8]}... (home_id={body.home_id}, chat_id={body.chat_id})")

            # Get the inserted record with all fields
            if not result.data:
                logger.error("❌ No data returned from database insert")
                return {
                    "success": False,
                    "error": "Image generated but failed to save record. Please contact support."
                }

            inserted_record = result.data[0]
            logger.info("✅ Image generation completed successfully!")

            # Return success response
            return {
                "success": True,
                "image": inserted_record
            }

        except Exception as db_error:
            logger.error(f"❌ Database insert error: {db_error}")
            return {
                "success": False,
                "error": f"Image generated but failed to save to database: {str(db_error)}"
            }

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise

    except Exception as e:
        # Catch-all for unexpected errors - return friendly error instead of 500
        import traceback
        logger.error(f"❌ Unexpected error in /generate: {str(e)}")
        logger.error(traceback.format_exc())

        return {
            "success": False,
            "error": "An unexpected error occurred during image generation. Please try again or contact support if the issue persists."
        }


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
