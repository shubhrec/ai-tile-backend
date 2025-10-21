"""
Pydantic models for request/response validation.
"""
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional
from datetime import datetime


class GenerateRequest(BaseModel):
    """Request payload for /generate endpoint."""
    tile_url: str = Field(..., description="URL of the tile image")
    home_url: str = Field(..., description="URL of the home/room image")
    prompt: str = Field(..., description="Text prompt for image generation", min_length=1)
    user_id: str = Field(..., description="Supabase user ID")
    tile_id: str = Field(..., description="Tile ID from the database")

    class Config:
        json_schema_extra = {
            "example": {
                "tile_url": "https://example.com/tile.jpg",
                "home_url": "https://example.com/room.jpg",
                "prompt": "Modern bathroom with marble tiles",
                "user_id": "user-123",
                "tile_id": "tile-456"
            }
        }


class GenerateResponse(BaseModel):
    """Response for /generate endpoint."""
    success: bool
    image_url: Optional[str] = None
    error: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "image_url": "https://storage.supabase.co/generated/image-123.jpg",
                "error": None
            }
        }


class GalleryImage(BaseModel):
    """Single gallery image record."""
    id: str
    tile_id: str
    user_id: str
    prompt: str
    image_url: str
    created_at: datetime


class GalleryResponse(BaseModel):
    """Response for /gallery endpoint."""
    success: bool
    images: list[GalleryImage] = []
    error: Optional[str] = None


class HealthResponse(BaseModel):
    """Response for /health endpoint."""
    status: str = "ok"
    version: str = "1.0.0"
