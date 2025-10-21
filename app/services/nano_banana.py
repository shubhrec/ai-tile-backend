"""
Nano Banana / Gemini 2.5 Flash Image API integration.
"""
import os
import base64
import httpx
from typing import Optional


class NanoBananaService:
    """Service for calling Gemini 2.5 Flash Image generation API."""

    def __init__(self):
        """Initialize Nano Banana service."""
        self.api_key = os.getenv("NANO_BANANA_API_KEY")
        if not self.api_key:
            raise ValueError("NANO_BANANA_API_KEY must be set")

        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent"
        self.timeout = 30.0

    async def generate_image(
        self,
        tile_url: str,
        home_url: str,
        prompt: str
    ) -> bytes:
        """
        Generate an image using Gemini 2.5 Flash Image API.

        Args:
            tile_url: URL of the tile image
            home_url: URL of the home/room image
            prompt: Text prompt for generation

        Returns:
            Binary image data

        Raises:
            Exception: If generation fails
        """
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            # Fetch images as base64 (optional - depends on API requirements)
            # For now, we'll pass URLs directly
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt}
                        ]
                    }
                ],
                "image_urls": [tile_url, home_url],
                "generationConfig": {
                    "temperature": 0.4,
                    "topK": 32,
                    "topP": 1,
                    "maxOutputTokens": 2048,
                }
            }

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.base_url,
                    json=payload,
                    headers=headers
                )

                if response.status_code != 200:
                    error_detail = response.text
                    raise Exception(
                        f"Nano Banana API returned {response.status_code}: {error_detail}"
                    )

                result = response.json()

                # Extract image data from response
                # The response structure may vary - adjust based on actual API
                image_data = self._extract_image_data(result)

                return image_data

        except httpx.TimeoutException:
            raise Exception("Image generation timed out after 30 seconds")
        except Exception as e:
            raise Exception(f"Image generation failed: {str(e)}")

    def _extract_image_data(self, api_response: dict) -> bytes:
        """
        Extract image binary data from API response.

        The Gemini API may return:
        - Base64-encoded image in response
        - URL to download image
        - Direct binary data

        Adjust this method based on actual API response format.
        """
        try:
            # Try to find base64 image data in response
            if "candidates" in api_response:
                for candidate in api_response["candidates"]:
                    if "content" in candidate:
                        parts = candidate["content"].get("parts", [])
                        for part in parts:
                            if "inline_data" in part:
                                b64_data = part["inline_data"]["data"]
                                return base64.b64decode(b64_data)

            # Try to find image URL in response
            if "image_url" in api_response:
                # Download image from URL
                import httpx
                with httpx.Client() as client:
                    img_response = client.get(api_response["image_url"])
                    return img_response.content

            raise Exception("Could not extract image data from API response")

        except Exception as e:
            raise Exception(f"Failed to extract image data: {str(e)}")


# Singleton instance
_nano_banana_service: Optional[NanoBananaService] = None


def get_nano_banana_service() -> NanoBananaService:
    """Get or create Nano Banana service instance."""
    global _nano_banana_service
    if _nano_banana_service is None:
        _nano_banana_service = NanoBananaService()
    return _nano_banana_service
