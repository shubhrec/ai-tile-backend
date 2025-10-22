# Intelligent Prompt System Documentation

## Overview

The backend now includes an intelligent prompt composition system that automatically builds comprehensive, context-aware prompts for AI image generation. The frontend only needs to send minimal user hints, and the backend handles all prompt engineering logic.

---

## Architecture

### New Files

1. **`app/services/prompt_builder.py`**
   - Core prompt composition logic
   - Surface detection algorithms
   - Edge case handling

2. **Updated `app/api/routes_generate.py`**
   - Integrated prompt builder
   - Enhanced logging
   - Explicit tile/house differentiation

---

## How It Works

### 1. Frontend Sends Minimal Request

**Old Way (Before):**
```json
{
  "tile_url": "https://...",
  "home_url": "https://...",
  "prompt": "Apply marble tiles to this bathroom wall with modern lighting and clean edges"
}
```

**New Way (Now):**
```json
{
  "tile_url": "https://...",
  "home_url": "https://...",
  "prompt": "bathroom",
  "surface": "auto"
}
```

Or even simpler:
```json
{
  "tile_url": "https://...",
  "home_url": "https://..."
}
```

### 2. Backend Builds Intelligent Prompt

The `build_prompt()` function automatically:

✅ Detects surface type (floor/wall/backsplash)
✅ Adds perspective & alignment instructions
✅ Includes lighting & shadow preservation rules
✅ Adds edge case handling
✅ Prevents object distortion
✅ Ensures realistic texture scaling

**Generated Prompt Example:**
```
You are an expert architectural visualizer and interior designer.
Your task is to combine the provided TILE image onto the HOUSE/ROOM image realistically.

CRITICAL REQUIREMENTS:
1. PERSPECTIVE & ALIGNMENT: Ensure perfect perspective alignment with the room's geometry...
2. LIGHTING & SHADOWS: Preserve and enhance existing shadows, lighting, and reflections...
3. EDGE HANDLING: Tiles must align cleanly at edges, corners, and transitions...
[... detailed instructions continue ...]

Based on the context, apply the tile design to the WALLS.
For bathroom or shower scenes, cover walls naturally while avoiding fixtures...

ADDITIONAL USER CONTEXT: modern bathroom

Generate the composite image showing the tile applied to the room with perfect realism...
```

---

## API Changes

### Updated Request Schema

```typescript
interface GenerateRequest {
  tile_url: string;        // Required
  home_url: string;        // Required
  prompt?: string;         // Optional (default: "")
  surface?: "auto" | "floor" | "wall" | "backsplash" | "shower";  // Optional (default: "auto")
}
```

### Request Examples

#### Example 1: Minimal Request (Auto-Detection)
```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "tile_url": "https://example.com/tile.jpg",
    "home_url": "https://example.com/bathroom.jpg"
  }'
```

**Backend will:**
- Auto-detect surface (likely "floor" unless hints suggest otherwise)
- Generate comprehensive prompt automatically

#### Example 2: With User Hint
```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "tile_url": "https://example.com/tile.jpg",
    "home_url": "https://example.com/bathroom.jpg",
    "prompt": "modern bathroom shower"
  }'
```

**Backend will:**
- Detect "bathroom" and "shower" keywords
- Apply tiles to WALLS
- Include user context in prompt

#### Example 3: Explicit Surface Override
```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "tile_url": "https://example.com/tile.jpg",
    "home_url": "https://example.com/kitchen.jpg",
    "prompt": "kitchen backsplash",
    "surface": "backsplash"
  }'
```

**Backend will:**
- Use explicitly specified "backsplash" surface
- Apply tiles between counters and cabinets

---

## Surface Detection Logic

### Automatic Detection

The system analyzes the `prompt` field for keywords:

| Keywords | Detected Surface |
|----------|------------------|
| bathroom, shower, bath, wall | `wall` |
| backsplash, kitchen | `backsplash` |
| floor, ground, flooring | `floor` |
| *default (no keywords)* | `floor` |

### Manual Override

Set `surface` explicitly to override auto-detection:
- `"auto"` - Let backend decide
- `"floor"` - Apply to floor
- `"wall"` - Apply to walls
- `"backsplash"` - Kitchen backsplash
- `"shower"` - Shower walls

---

## Prompt Engineering Features

### Edge Case Handling

The prompt builder automatically includes instructions for:

1. **Perspective Alignment**
   - Follow room geometry
   - Correct vanishing points
   - Natural plane following

2. **Object Preservation**
   - Don't tile over furniture
   - Preserve people, pets
   - Avoid doors, windows
   - Keep fixtures intact

3. **Lighting & Shadows**
   - Match ambient lighting
   - Preserve shadows
   - Add realistic reflections

4. **Edge & Corner Handling**
   - Clean alignment
   - Consistent grout lines
   - Natural transitions

5. **Texture Scaling**
   - Appropriate size for room
   - No stretching/compression
   - Realistic proportions

---

## Explicit Image Differentiation

The backend now sends images with clear labels to the AI:

```python
parts=[
    types.Part.from_text(text=ai_prompt),
    types.Part.from_text(text="The following image is the TILE design that should be applied:"),
    types.Part(inline_data=types.Blob(mime_type="image/jpeg", data=tile_bytes)),
    types.Part.from_text(text="The following image is the HOUSE/ROOM where the tile should be installed:"),
    types.Part(inline_data=types.Blob(mime_type="image/jpeg", data=home_bytes)),
]
```

This ensures the AI model clearly understands which image is the tile and which is the room.

---

## Logging & Debugging

### What Gets Logged

Every generation request logs:

```
🎨 Generated AI Prompt:
[Full prompt text...]

📝 User hint: 'bathroom'
🎯 Surface: auto
📤 Sending request to Gemini API with differentiated images
✅ Generated image saved locally: generated/generated_output_1732189234.jpg
✅ Uploaded to Supabase Storage: generated_output_1732189234.jpg
✅ Public URL: https://...
✅ Database record inserted: [...]
```

### View Logs

Start server with log output:
```bash
uvicorn app.main:app --reload --log-level info
```

Or check application logs in production.

---

## Frontend Integration

### Simple Integration

```typescript
// Minimal request - let backend handle everything
async function generateTileVisualization(tileUrl: string, homeUrl: string) {
  const response = await fetch('http://localhost:8000/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      tile_url: tileUrl,
      home_url: homeUrl,
    }),
  });

  return response.json();
}
```

### With User Context

```typescript
// Add optional user hint
async function generateWithContext(
  tileUrl: string,
  homeUrl: string,
  userHint: string
) {
  const response = await fetch('http://localhost:8000/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      tile_url: tileUrl,
      home_url: homeUrl,
      prompt: userHint,  // e.g., "modern bathroom"
    }),
  });

  return response.json();
}
```

### With Surface Override

```typescript
// Explicit surface selection
async function generateWithSurface(
  tileUrl: string,
  homeUrl: string,
  surface: 'floor' | 'wall' | 'backsplash'
) {
  const response = await fetch('http://localhost:8000/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      tile_url: tileUrl,
      home_url: homeUrl,
      surface: surface,
    }),
  });

  return response.json();
}
```

---

## Advanced Usage

### Custom Prompt Builder

For advanced customization, use `build_advanced_prompt()`:

```python
from app.services.prompt_builder import build_advanced_prompt

prompt = build_advanced_prompt(
    user_hint="luxury bathroom renovation",
    surface="wall",
    room_type="bathroom",
    style_preference="modern minimalist"
)
```

### Surface Detection Only

```python
from app.services.prompt_builder import detect_surface_from_hint

surface = detect_surface_from_hint("kitchen backsplash")
# Returns: "backsplash"
```

---

## Benefits

### For Developers

✅ **Reduced frontend complexity** - No prompt engineering needed
✅ **Centralized logic** - All prompt rules in one place
✅ **Easy updates** - Change prompts without frontend deploy
✅ **Better logging** - Full visibility into AI requests

### For Users

✅ **Better results** - Professional prompt engineering
✅ **Consistent quality** - Same instructions every time
✅ **Smart detection** - Auto-detects surface type
✅ **Edge case handling** - Prevents common mistakes

### For Business

✅ **Maintainable** - Single source of truth
✅ **Testable** - Unit test prompt logic
✅ **Auditable** - Full logging of all prompts
✅ **Optimizable** - A/B test different prompts

---

## Testing

### Test Prompt Generation

```python
from app.services.prompt_builder import build_prompt

# Test bathroom detection
prompt = build_prompt(user_hint="modern bathroom", surface="auto")
assert "WALLS" in prompt

# Test floor default
prompt = build_prompt(user_hint="living room", surface="auto")
assert "FLOOR" in prompt

# Test explicit override
prompt = build_prompt(user_hint="", surface="backsplash")
assert "backsplash" in prompt.lower()
```

### Test Full Endpoint

```bash
# Test with minimal request
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "tile_url": "https://example.com/tile.jpg",
    "home_url": "https://example.com/room.jpg"
  }'

# Test with hint
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "tile_url": "https://example.com/tile.jpg",
    "home_url": "https://example.com/bathroom.jpg",
    "prompt": "shower walls"
  }'
```

---

## Migration Guide

### From Old System

**Before:**
```typescript
// Frontend had to build detailed prompt
const prompt = `
  Apply these tiles to the bathroom wall.
  Ensure perfect alignment and lighting.
  Don't tile over fixtures.
  Maintain realistic perspective.
  ...
`;

fetch('/generate', {
  body: JSON.stringify({ tile_url, home_url, prompt })
});
```

**After:**
```typescript
// Frontend sends minimal hint
fetch('/generate', {
  body: JSON.stringify({
    tile_url,
    home_url,
    prompt: "bathroom"  // or even omit this
  })
});
```

### Backward Compatibility

The system is **backward compatible**. Old detailed prompts will still work:

```json
{
  "prompt": "Apply marble tiles to bathroom wall with perfect alignment..."
}
```

The backend will use this as the `user_hint` and still add its own instructions.

---

## Future Enhancements

Potential additions:

- **Style presets** - "modern", "traditional", "minimalist"
- **Room type detection** - Auto-detect from image
- **Multi-language support** - Translate hints
- **Prompt versioning** - A/B test different prompts
- **User feedback loop** - Improve prompts based on results

---

## Troubleshooting

### Issue: Wrong surface detected

**Solution:** Use explicit `surface` parameter
```json
{ "surface": "wall" }
```

### Issue: Results not realistic enough

**Check logs:** Ensure prompt is being generated correctly
```bash
tail -f logs/app.log | grep "Generated AI Prompt"
```

### Issue: Tiles applied to wrong area

**Add more context:**
```json
{ "prompt": "kitchen backsplash between counter and cabinets" }
```

---

## Summary

The intelligent prompt system:

✅ Moves prompt engineering to backend
✅ Auto-detects surface types
✅ Handles edge cases automatically
✅ Provides explicit image differentiation
✅ Includes comprehensive logging
✅ Simplifies frontend integration
✅ Maintains backward compatibility

Frontend developers can now focus on UI/UX while the backend handles all AI prompt complexity!
