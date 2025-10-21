# Upload & File Management API Documentation

## Overview
New secure backend endpoints for handling Supabase Storage operations. All upload and retrieval logic has been moved from the frontend to the backend for better security.

## Endpoints

### 1. Upload File to Storage

**Endpoint:** `POST /api/upload/{bucket}`

**Description:** Upload an image file to a specified Supabase Storage bucket.

**Parameters:**
- `bucket` (path parameter): Bucket name (e.g., `tiles`, `homes`, `generated`)
- `file` (form-data): Image file to upload

**Request Example (cURL):**
```bash
curl -X POST http://localhost:8000/api/upload/tiles \
  -F "file=@/path/to/image.jpg"
```

**Request Example (JavaScript/Fetch):**
```javascript
const formData = new FormData();
formData.append('file', fileInput.files[0]);

const response = await fetch('http://localhost:8000/api/upload/tiles', {
  method: 'POST',
  body: formData,
});

const data = await response.json();
console.log(data);
```

**Success Response:**
```json
{
  "success": true,
  "url": "https://yourproject.supabase.co/storage/v1/object/public/tiles/1732189234_tile.jpg"
}
```

**Error Response:**
```json
{
  "success": false,
  "error": "Upload failed: Bucket not found"
}
```

**Status Codes:**
- `200` - Success
- `400` - Invalid file or upload error
- `500` - Server configuration error

---

### 2. List Files in Bucket

**Endpoint:** `GET /api/list/{bucket}`

**Description:** Retrieve a list of all files in a specified Supabase Storage bucket.

**Parameters:**
- `bucket` (path parameter): Bucket name (e.g., `tiles`, `homes`, `generated`)

**Request Example (cURL):**
```bash
curl http://localhost:8000/api/list/tiles
```

**Request Example (JavaScript/Fetch):**
```javascript
const response = await fetch('http://localhost:8000/api/list/tiles');
const data = await response.json();
console.log(data.files);
```

**Success Response:**
```json
{
  "success": true,
  "files": [
    "https://yourproject.supabase.co/storage/v1/object/public/tiles/1732189234_tile1.jpg",
    "https://yourproject.supabase.co/storage/v1/object/public/tiles/1732189456_tile2.jpg",
    "https://yourproject.supabase.co/storage/v1/object/public/tiles/1732189678_tile3.jpg"
  ]
}
```

**Error Response:**
```json
{
  "success": false,
  "error": "Failed to list files: Bucket not found",
  "files": []
}
```

**Status Codes:**
- `200` - Success
- `400` - Bucket not found or access error
- `500` - Server configuration error

---

## Common Bucket Names

| Bucket | Purpose |
|--------|---------|
| `tiles` | User-uploaded tile images |
| `homes` | User-uploaded home/room images |
| `generated` | AI-generated visualization images |

---

## Integration with Frontend

### Example: Upload Tile Image

```typescript
// React/Next.js component
async function handleTileUpload(file: File) {
  const formData = new FormData();
  formData.append('file', file);

  try {
    const response = await fetch('http://localhost:8000/api/upload/tiles', {
      method: 'POST',
      body: formData,
    });

    const data = await response.json();

    if (data.success) {
      console.log('Tile uploaded:', data.url);
      // Save data.url to your state or database
    } else {
      console.error('Upload failed:', data.error);
    }
  } catch (error) {
    console.error('Network error:', error);
  }
}
```

### Example: Fetch All Tiles

```typescript
// React/Next.js component
async function fetchAllTiles() {
  try {
    const response = await fetch('http://localhost:8000/api/list/tiles');
    const data = await response.json();

    if (data.success) {
      console.log('Available tiles:', data.files);
      // Display tiles in your UI
      setTiles(data.files);
    } else {
      console.error('Failed to fetch tiles:', data.error);
    }
  } catch (error) {
    console.error('Network error:', error);
  }
}
```

---

## Security Features

✅ **Server-side validation** - Only image files are allowed
✅ **Unique filenames** - Timestamp-based naming prevents conflicts
✅ **Service role authentication** - Uses Supabase service key (not exposed to frontend)
✅ **CORS protection** - Only configured origins can access these endpoints
✅ **Error handling** - Graceful error messages without exposing sensitive info

---

## Testing

### Using FastAPI Docs UI

1. Start the server: `uvicorn app.main:app --reload`
2. Open: `http://localhost:8000/docs`
3. Navigate to "uploads" section
4. Try out `/api/upload/{bucket}` and `/api/list/{bucket}`

### Using Postman

**Upload Request:**
- Method: `POST`
- URL: `http://localhost:8000/api/upload/tiles`
- Body: form-data
  - Key: `file` (type: File)
  - Value: Select an image file

**List Request:**
- Method: `GET`
- URL: `http://localhost:8000/api/list/tiles`

---

## Environment Configuration

Ensure these variables are set in your `.env` file:

```env
SUPABASE_URL=https://yourproject.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
ALLOWED_ORIGINS=http://localhost:3000,https://your-frontend-domain.com
```

---

## Error Handling

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Supabase credentials not configured` | Missing env vars | Add `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` |
| `Only image files are allowed` | Non-image file uploaded | Upload only JPG, PNG, etc. |
| `Upload failed: Bucket not found` | Bucket doesn't exist | Create bucket in Supabase Storage |
| `CORS error` | Frontend domain not allowed | Add domain to `ALLOWED_ORIGINS` |

---

## Next Steps

1. **Update your frontend** to use these endpoints instead of direct Supabase calls
2. **Remove Supabase client** from frontend code
3. **Add authentication** (optional) to protect uploads with user tokens
4. **Implement file deletion** endpoint if needed
5. **Add file size limits** for production use

---

## File Naming Convention

All uploaded files are automatically renamed with this pattern:
```
{timestamp}_{original_filename}
```

Example:
- Original: `tile.jpg`
- Stored as: `1732189234_tile.jpg`

This ensures uniqueness and prevents overwriting existing files.
