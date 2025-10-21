"""
Gallery endpoint for retrieving generated images.
"""
from fastapi import APIRouter, HTTPException, Query
from app.models.schemas import GalleryResponse, GalleryImage
from app.services.supabase_client import get_supabase_service

router = APIRouter()


@router.get("/gallery", response_model=GalleryResponse)
async def get_gallery(tile_id: str = Query(..., description="Tile ID to retrieve images for")):
    """
    Retrieve all generated images for a specific tile.

    Returns images ordered by creation date (newest first).
    """
    try:
        # Initialize Supabase service
        supabase = get_supabase_service()

        # Retrieve gallery images
        images_data = await supabase.get_gallery_images(tile_id)

        # Convert to Pydantic models
        images = [GalleryImage(**img) for img in images_data]

        return GalleryResponse(
            success=True,
            images=images,
            error=None
        )

    except Exception as e:
        # Log error (in production, use proper logging)
        print(f"Error in /gallery: {str(e)}")

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
