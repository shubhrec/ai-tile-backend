"""
Intelligent prompt builder for AI tile visualization.

This module constructs detailed, context-aware prompts for the image generation model
to realistically apply tile designs onto house/room images.
"""
import logging

logger = logging.getLogger(__name__)


def build_prompt(
    user_hint: str = "",
    surface: str = "auto",
    tile_size: str = None,
    tile_type: str = None
) -> str:
    """
    Builds a robust AI prompt that guides the model to realistically apply a tile design onto a house image.

    Args:
        user_hint: Optional user context or note (e.g., "modern bathroom", "kitchen backsplash")
        surface: Target surface - "auto", "floor", "wall", "backsplash", "shower"
        tile_size: Tile size in mm (e.g., "600x600")
        tile_type: Tile type/material (e.g., "ceramic tile", "marble", "porcelain")

    Returns:
        Comprehensive prompt string for the AI model
    """
    # Automatic surface detection logic
    hint_lower = user_hint.lower() if user_hint else ""

    if surface == "auto":
        if any(word in hint_lower for word in ["bathroom", "shower", "bath", "wall", "backsplash"]):
            surface_type = "wall"
            region_hint = "vertical surfaces"
        else:
            surface_type = "floor"
            region_hint = "bottom part of the image"
        logger.info(f"Auto-detected surface: {surface_type} (from hint: '{user_hint}')")
    else:
        surface_type = surface
        region_hint = "bottom part of the image" if surface == "floor" else "vertical surfaces"
        logger.info(f"User-specified surface: {surface}")

    # Set defaults for tile metadata
    tile_type = tile_type or "ceramic tile"
    tile_size = tile_size or "600x600"

    logger.info(f"Tile metadata - Size: {tile_size}, Type: {tile_type}")

    # Build structured prompt
    base_prompt = f"""You are creating a photorealistic render to visualize how a house would look
with a specific tile applied.

- Use the provided home photo as the base image.
- Apply the tile image only on the appropriate surface ({surface_type}), such as the {region_hint}.
- Preserve the rest of the scene exactly as in the original photo:
  lighting, walls, shadows, and objects remain unchanged.

Tile details:
- Tile size: {tile_size} mm
- Tile type: {tile_type} (e.g., matte, glossy, marble, wood, stone)
- Maintain correct aspect ratio and pattern alignment according to tile size.
- Do not resize, distort, or duplicate the tile pattern unnaturally.
- Ensure tiles are evenly spaced with realistic grout lines.
- Keep tile colour and texture identical to the original tile image.
- If the tile is large (≥800mm), show fewer but larger tiles;
  if small (≤300mm), repeat more frequently for a natural layout.
- The floor/wall edges must align properly—no stretched or warped tiles.

Output requirements:
- Produce a realistic composite as if professionally rendered.
- Keep the tile pattern crisp and consistent.
- Avoid generating additional tiles or reflections not present in the original.
"""

    # Append user hint if provided
    if user_hint and user_hint.strip():
        base_prompt += f"\nUser request: {user_hint.strip()}\n"
        logger.info(f"User hint included: '{user_hint.strip()}'")

    return base_prompt


def detect_surface_from_hint(user_hint: str) -> str:
    """
    Detect the intended surface from user hint.

    Args:
        user_hint: User-provided context string

    Returns:
        Detected surface type: "floor", "wall", "backsplash", or "auto"
    """
    hint_lower = user_hint.lower() if user_hint else ""

    # Wall-based keywords
    wall_keywords = ["bathroom", "shower", "bath", "wall", "vertical"]
    if any(word in hint_lower for word in wall_keywords):
        return "wall"

    # Backsplash-specific
    if "backsplash" in hint_lower or "kitchen" in hint_lower:
        return "backsplash"

    # Floor-based keywords (default)
    floor_keywords = ["floor", "ground", "flooring"]
    if any(word in hint_lower for word in floor_keywords):
        return "floor"

    return "auto"


def build_advanced_prompt(
    user_hint: str = "",
    surface: str = "auto",
    room_type: str = "auto",
    style_preference: str = "",
    tile_size: str = None,
    tile_type: str = None
) -> str:
    """
    Advanced prompt builder with additional customization options.

    Args:
        user_hint: User context or note
        surface: Target surface (auto, floor, wall, backsplash, shower)
        room_type: Type of room (auto, bathroom, kitchen, living room, etc.)
        style_preference: Style guidance (modern, traditional, minimalist, etc.)
        tile_size: Tile size in mm (e.g., "600x600")
        tile_type: Tile type/material (e.g., "ceramic tile", "marble", "porcelain")

    Returns:
        Detailed prompt string
    """
    prompt = build_prompt(user_hint, surface, tile_size, tile_type)

    if style_preference:
        prompt += f"\n\nSTYLE GUIDANCE: Emphasize a {style_preference} aesthetic in the final visualization."
        logger.info(f"Style preference: {style_preference}")

    if room_type != "auto":
        prompt += f"\n\nROOM TYPE: This is a {room_type}. Tailor the tile application accordingly."
        logger.info(f"Room type specified: {room_type}")

    return prompt
