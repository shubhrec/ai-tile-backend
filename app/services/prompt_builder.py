"""
Intelligent prompt builder for AI tile visualization.

This module constructs detailed, context-aware prompts for the image generation model
to realistically apply tile designs onto house/room images.
"""
import logging

logger = logging.getLogger(__name__)


def build_prompt(user_hint: str = "", surface: str = "auto") -> str:
    """
    Builds a robust AI prompt that guides the model to realistically apply a tile design onto a house image.

    Args:
        user_hint: Optional user context or note (e.g., "modern bathroom", "kitchen backsplash")
        surface: Target surface - "auto", "floor", "wall", "backsplash", "shower"

    Returns:
        Comprehensive prompt string for the AI model

    Handles edge cases such as:
    - Determining whether tiles belong on floor or wall
    - Ensuring edges align cleanly
    - Avoiding distortion of objects (furniture, people, etc.)
    - Maintaining realistic lighting and perspective
    - Differentiating tile vs house input clearly
    - Default assumption: floor unless 'bathroom', 'wall', 'kitchen backsplash' detected
    """

    # Base instruction set for the AI model
    base_prompt = (
        "You are an expert architectural visualizer and interior designer. "
        "Your task is to combine the provided TILE image onto the HOUSE/ROOM image realistically. "
        "\n\n"
        "CRITICAL REQUIREMENTS:\n"
        "1. PERSPECTIVE & ALIGNMENT: Ensure perfect perspective alignment with the room's geometry. "
        "Tiles must follow the floor or wall plane naturally, with correct vanishing points.\n"
        "2. LIGHTING & SHADOWS: Preserve and enhance existing shadows, lighting, and reflections. "
        "Match the room's ambient lighting on the tile surface.\n"
        "3. EDGE HANDLING: Tiles must align cleanly at edges, corners, and transitions. "
        "Grout lines should be consistent and realistic.\n"
        "4. OBJECT PRESERVATION: Do NOT distort or tile over furniture, people, fixtures, doors, windows, or natural elements. "
        "These must remain untouched and realistic.\n"
        "5. TEXTURE & SCALE: Maintain the tile texture's scale appropriately for the room size. "
        "Avoid stretching or compressing the tile pattern unnaturally.\n"
        "6. SURFACE SELECTION: "
    )

    # Automatic surface detection logic
    if surface == "auto":
        # Analyze user hint for surface clues
        hint_lower = user_hint.lower() if user_hint else ""

        if any(word in hint_lower for word in ["bathroom", "shower", "bath", "wall", "backsplash"]):
            detected_surface = "wall"
            base_prompt += (
                "Based on the context, apply the tile design to the WALLS. "
                "For bathroom or shower scenes, cover walls naturally while avoiding fixtures. "
                "For kitchen backsplash, apply tiles between counters and cabinets.\n"
            )
        else:
            detected_surface = "floor"
            base_prompt += (
                "Apply the tile design to the FLOOR surface. "
                "Ensure tiles follow the floor plane with correct perspective. "
                "Avoid tiling over rugs, furniture legs, or floor-level objects.\n"
            )

        logger.info(f"Auto-detected surface: {detected_surface} (from hint: '{user_hint}')")
    else:
        # User explicitly specified surface
        base_prompt += f"Apply the tile design specifically to the {surface.upper()}.\n"
        logger.info(f"User-specified surface: {surface}")

    # Additional constraints
    base_prompt += (
        "\n"
        "7. REALISM: Focus on showing how the tile will look AFTER professional installation. "
        "The result should be photorealistic and indistinguishable from a real renovation.\n"
        "8. BOUNDARIES: Do NOT tile over:\n"
        "   - Ceilings (unless explicitly a ceiling tile scenario)\n"
        "   - Doors or door frames\n"
        "   - Windows or window frames\n"
        "   - Furniture or appliances\n"
        "   - Decorative elements\n"
        "   - People or pets\n"
        "\n"
        "9. OUTPUT QUALITY: Generate a high-quality, professional visualization suitable for "
        "client presentations or renovation planning.\n"
    )

    # Append user hint if provided
    if user_hint and user_hint.strip():
        base_prompt += f"\n\nADDITIONAL USER CONTEXT: {user_hint.strip()}\n"
        logger.info(f"User hint included: '{user_hint.strip()}'")

    # Final instruction
    base_prompt += (
        "\n"
        "Generate the composite image showing the tile applied to the room with perfect realism and attention to detail."
    )

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
    style_preference: str = ""
) -> str:
    """
    Advanced prompt builder with additional customization options.

    Args:
        user_hint: User context or note
        surface: Target surface (auto, floor, wall, backsplash, shower)
        room_type: Type of room (auto, bathroom, kitchen, living room, etc.)
        style_preference: Style guidance (modern, traditional, minimalist, etc.)

    Returns:
        Detailed prompt string
    """
    prompt = build_prompt(user_hint, surface)

    if style_preference:
        prompt += f"\n\nSTYLE GUIDANCE: Emphasize a {style_preference} aesthetic in the final visualization."
        logger.info(f"Style preference: {style_preference}")

    if room_type != "auto":
        prompt += f"\n\nROOM TYPE: This is a {room_type}. Tailor the tile application accordingly."
        logger.info(f"Room type specified: {room_type}")

    return prompt
