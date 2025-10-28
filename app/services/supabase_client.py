"""
Supabase client wrapper for storage and database operations.
"""
import os
from typing import Optional, List, Dict, Any
from supabase import create_client, Client
from datetime import datetime
import uuid


class SupabaseService:
    """Service for interacting with Supabase storage and database."""

    def __init__(self):
        """Initialize Supabase client."""
        self.url = os.getenv("SUPABASE_URL")
        self.key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        self.bucket = os.getenv("SUPABASE_STORAGE_BUCKET", "generated")

        if not self.url or not self.key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")

        self.client: Client = create_client(self.url, self.key)

    async def upload_image(self, image_data: bytes, file_extension: str = "jpg") -> str:
        """
        Upload image to Supabase Storage.

        Args:
            image_data: Binary image data
            file_extension: File extension (default: jpg)

        Returns:
            Public URL of the uploaded image
        """
        try:
            # Generate unique filename
            filename = f"{uuid.uuid4()}.{file_extension}"

            # Upload to storage
            self.client.storage.from_(self.bucket).upload(
                filename,
                image_data,
                {"content-type": f"image/{file_extension}"}
            )

            # Get optimized public URL with CDN caching and compression
            public_url = f"{self.url}/storage/v1/render/image/public/{self.bucket}/{filename}?width=512&quality=80"

            return public_url
        except Exception as e:
            raise Exception(f"Failed to upload image to Supabase: {str(e)}")

    async def insert_generated_image(
        self,
        tile_id: str,
        user_id: str,
        prompt: str,
        image_url: str
    ) -> Dict[str, Any]:
        """
        Insert a record into the generated_images table.

        Args:
            tile_id: ID of the tile used
            user_id: ID of the user
            prompt: Generation prompt
            image_url: URL of the generated image

        Returns:
            Inserted record
        """
        try:
            data = {
                "tile_id": tile_id,
                "user_id": user_id,
                "prompt": prompt,
                "image_url": image_url,
                "created_at": datetime.utcnow().isoformat()
            }

            result = self.client.table("generated_images").insert(data).execute()

            if not result.data:
                raise Exception("No data returned from insert operation")

            return result.data[0]
        except Exception as e:
            raise Exception(f"Failed to insert generated image record: {str(e)}")

    async def get_gallery_images(self, tile_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve all generated images for a specific tile.

        Args:
            tile_id: ID of the tile

        Returns:
            List of image records ordered by created_at desc
        """
        try:
            result = self.client.table("generated_images")\
                .select("*")\
                .eq("tile_id", tile_id)\
                .order("created_at", desc=True)\
                .execute()

            return result.data if result.data else []
        except Exception as e:
            raise Exception(f"Failed to retrieve gallery images: {str(e)}")


# Singleton instance
_supabase_service: Optional[SupabaseService] = None
_supabase_client: Optional[Client] = None


def get_supabase_service() -> SupabaseService:
    """Get or create Supabase service instance."""
    global _supabase_service
    if _supabase_service is None:
        _supabase_service = SupabaseService()
    return _supabase_service


def get_supabase_client() -> Client:
    """Get or create Supabase client instance for direct database access."""
    global _supabase_client
    if _supabase_client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not url or not key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")

        _supabase_client = create_client(url, key)
    return _supabase_client


# Export client for direct use in routes
supabase = get_supabase_client()
