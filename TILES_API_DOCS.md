# Tiles API Documentation

## Overview

The Tiles API provides endpoints for persisting user-specific tiles in Supabase. Tiles are linked to authenticated users and persist across page reloads, devices, and incognito sessions.

All endpoints require authentication via JWT Bearer token.

---

## Endpoints

### POST /api/tiles

Add a new tile for the authenticated user.

**Authentication:** Required (Bearer token)

**Request Body:**
```json
{
  "image_url": "https://waqzrjsczmlvkapbkcno.supabase.co/storage/v1/object/public/tiles/123_tile.jpg",
  "name": "Modern Bathroom Tile"  // Optional
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "tile": {
    "id": 42,
    "user_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "name": "Modern Bathroom Tile",
    "image_url": "https://waqzrjsczmlvkapbkcno.supabase.co/storage/v1/object/public/tiles/123_tile.jpg",
    "created_at": "2025-10-22T17:30:00.000Z"
  }
}
```

**Error Responses:**

- `400 Bad Request` - Missing or invalid image_url
- `401 Unauthorized` - Missing or invalid authentication token
- `500 Internal Server Error` - Database operation failed

**Example with cURL:**
```bash
curl -X POST http://localhost:8000/api/tiles \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "image_url": "https://waqzrjsczmlvkapbkcno.supabase.co/storage/v1/object/public/tiles/tile.jpg",
    "name": "Kitchen Backsplash"
  }'
```

**Example with JavaScript:**
```javascript
const response = await fetch('http://localhost:8000/api/tiles', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    image_url: 'https://waqzrjsczmlvkapbkcno.supabase.co/storage/v1/object/public/tiles/tile.jpg',
    name: 'Kitchen Backsplash'
  })
});

const result = await response.json();
console.log('Created tile:', result.tile);
```

---

### GET /api/tiles

Get all tiles for the authenticated user.

**Authentication:** Required (Bearer token)

**Query Parameters:** None

**Response (200 OK):**
```json
{
  "tiles": [
    {
      "id": 42,
      "user_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "name": "Modern Bathroom Tile",
      "image_url": "https://waqzrjsczmlvkapbkcno.supabase.co/storage/v1/object/public/tiles/tile1.jpg",
      "created_at": "2025-10-22T17:30:00.000Z"
    },
    {
      "id": 41,
      "user_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "name": "Kitchen Backsplash",
      "image_url": "https://waqzrjsczmlvkapbkcno.supabase.co/storage/v1/object/public/tiles/tile2.jpg",
      "created_at": "2025-10-22T16:15:00.000Z"
    }
  ]
}
```

**Notes:**
- Tiles are ordered by `created_at` descending (newest first)
- Only returns tiles belonging to the authenticated user
- Returns empty array if user has no tiles

**Error Responses:**

- `401 Unauthorized` - Missing or invalid authentication token
- `500 Internal Server Error` - Database operation failed

**Example with cURL:**
```bash
curl -X GET http://localhost:8000/api/tiles \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Example with JavaScript:**
```javascript
const response = await fetch('http://localhost:8000/api/tiles', {
  method: 'GET',
  headers: {
    'Authorization': `Bearer ${token}`
  }
});

const result = await response.json();
console.log(`User has ${result.tiles.length} tiles`);
result.tiles.forEach(tile => {
  console.log(`- ${tile.name || 'Unnamed'}: ${tile.image_url}`);
});
```

---

### DELETE /api/tiles/{tile_id}

Delete a tile by its ID (only if owned by the authenticated user).

**Authentication:** Required (Bearer token)

**URL Parameters:**
- `tile_id` (integer) - The ID of the tile to delete

**Response (200 OK):**
```json
{
  "success": true,
  "deleted_id": 42
}
```

**Notes:**
- Only the tile's owner can delete it (verified by user_id from JWT)
- Automatically deletes the associated image file from Supabase Storage
- If storage deletion fails, the database record is still deleted (graceful degradation)

**Error Responses:**

- `401 Unauthorized` - Missing or invalid authentication token
- `404 Not Found` - Tile not found or not owned by user
- `500 Internal Server Error` - Database operation failed

**Example with cURL:**
```bash
curl -X DELETE http://localhost:8000/api/tiles/42 \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Example with JavaScript:**
```javascript
const response = await fetch(`http://localhost:8000/api/tiles/${tileId}`, {
  method: 'DELETE',
  headers: {
    'Authorization': `Bearer ${token}`
  }
});

const result = await response.json();
if (result.success) {
  console.log(`Tile ${result.deleted_id} deleted successfully`);
}
```

**Security:**
- Users cannot delete tiles they don't own
- Double-check with both database query and user_id verification
- RLS policies provide an additional layer of protection

---

## Complete Workflow Example

### 1. Upload a Tile Image

First, upload the tile image to Supabase Storage:

```javascript
const formData = new FormData();
formData.append('file', tileImageFile);

const uploadResponse = await fetch('http://localhost:8000/api/upload/tiles', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`
  },
  body: formData
});

const uploadResult = await uploadResponse.json();
const imageUrl = uploadResult.url;
```

### 2. Save Tile to Database

Then, save the tile reference to the database:

```javascript
const addTileResponse = await fetch('http://localhost:8000/api/tiles', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    image_url: imageUrl,
    name: 'My Custom Tile'
  })
});

const addTileResult = await addTileResponse.json();
console.log('Tile saved:', addTileResult.tile);
```

### 3. Retrieve User's Tiles

Later, retrieve all tiles for the user:

```javascript
const getTilesResponse = await fetch('http://localhost:8000/api/tiles', {
  method: 'GET',
  headers: {
    'Authorization': `Bearer ${token}`
  }
});

const getTilesResult = await getTilesResponse.json();
console.log('User tiles:', getTilesResult.tiles);
```

---

## React Component Example

```typescript
// hooks/useTiles.ts
import { useState, useEffect } from 'react';
import { createClient } from '@supabase/supabase-js';

const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
const API_URL = 'http://localhost:8000';

interface Tile {
  id: number;
  user_id: string;
  name: string;
  image_url: string;
  created_at: string;
}

export function useTiles() {
  const [tiles, setTiles] = useState<Tile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Get auth token
  async function getToken() {
    const { data } = await supabase.auth.getSession();
    return data.session?.access_token;
  }

  // Fetch tiles
  async function fetchTiles() {
    try {
      setLoading(true);
      setError(null);

      const token = await getToken();
      if (!token) throw new Error('Not authenticated');

      const response = await fetch(`${API_URL}/api/tiles`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (!response.ok) throw new Error('Failed to fetch tiles');

      const result = await response.json();
      setTiles(result.tiles);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  // Add tile
  async function addTile(imageUrl: string, name: string = '') {
    try {
      const token = await getToken();
      if (!token) throw new Error('Not authenticated');

      const response = await fetch(`${API_URL}/api/tiles`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ image_url: imageUrl, name })
      });

      if (!response.ok) throw new Error('Failed to add tile');

      const result = await response.json();
      setTiles(prev => [result.tile, ...prev]);
      return result.tile;
    } catch (err) {
      setError(err.message);
      throw err;
    }
  }

  // Upload and add tile
  async function uploadAndAddTile(file: File, name: string = '') {
    try {
      // 1. Upload to Supabase Storage
      const token = await getToken();
      if (!token) throw new Error('Not authenticated');

      const formData = new FormData();
      formData.append('file', file);

      const uploadResponse = await fetch(`${API_URL}/api/upload/tiles`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: formData
      });

      if (!uploadResponse.ok) throw new Error('Failed to upload file');

      const uploadResult = await uploadResponse.json();

      // 2. Save to database
      return await addTile(uploadResult.url, name);
    } catch (err) {
      setError(err.message);
      throw err;
    }
  }

  // Delete tile
  async function deleteTile(tileId: number) {
    try {
      const token = await getToken();
      if (!token) throw new Error('Not authenticated');

      const response = await fetch(`${API_URL}/api/tiles/${tileId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (!response.ok) {
        if (response.status === 404) {
          throw new Error('Tile not found or not owned by user');
        }
        throw new Error('Failed to delete tile');
      }

      const result = await response.json();

      // Remove from local state
      setTiles(prev => prev.filter(tile => tile.id !== tileId));

      return result;
    } catch (err) {
      setError(err.message);
      throw err;
    }
  }

  useEffect(() => {
    fetchTiles();
  }, []);

  return {
    tiles,
    loading,
    error,
    refetch: fetchTiles,
    addTile,
    uploadAndAddTile,
    deleteTile
  };
}
```

**Usage in Component:**

```typescript
// components/TileGallery.tsx
import { useTiles } from '@/hooks/useTiles';

export function TileGallery() {
  const { tiles, loading, error, uploadAndAddTile, deleteTile } = useTiles();

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    try {
      await uploadAndAddTile(file, 'New Tile');
      alert('Tile added successfully!');
    } catch (err) {
      alert('Failed to add tile');
    }
  }

  async function handleDelete(tileId: number) {
    if (!confirm('Are you sure you want to delete this tile?')) return;

    try {
      await deleteTile(tileId);
      alert('Tile deleted successfully!');
    } catch (err) {
      alert('Failed to delete tile');
    }
  }

  if (loading) return <div>Loading tiles...</div>;
  if (error) return <div>Error: {error}</div>;

  return (
    <div>
      <input type="file" accept="image/*" onChange={handleFileUpload} />

      <div className="grid grid-cols-3 gap-4">
        {tiles.map(tile => (
          <div key={tile.id} className="tile-card">
            <img src={tile.image_url} alt={tile.name} />
            <p>{tile.name || 'Unnamed'}</p>
            <button onClick={() => handleDelete(tile.id)} className="delete-btn">
              Delete
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
```

---

## Database Schema

```sql
CREATE TABLE tiles (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name TEXT NOT NULL DEFAULT '',
    image_url TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);
```

**Indexes:**
- `idx_tiles_user_id` on `user_id` - Fast user-specific queries
- `idx_tiles_created_at` on `created_at DESC` - Efficient ordering

**Row Level Security (RLS):**
- Users can only view their own tiles
- Users can only insert/update/delete their own tiles
- Automatically enforced by Supabase

---

## Security

### Authentication

All endpoints require a valid Supabase JWT token in the Authorization header:

```
Authorization: Bearer eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Authorization

- Row Level Security (RLS) ensures users can only access their own tiles
- `user_id` is automatically extracted from JWT and used for queries
- No way for users to access tiles belonging to other users

### Data Validation

- `image_url` is required and validated
- `name` is optional and defaults to empty string
- `user_id` is automatically set from authenticated user

---

## Logging

All operations are logged with the authenticated user ID:

```
🔐 User abc12345... adding tile: Kitchen Backsplash
✅ Tile created: ID=42 for user abc12345...

🔐 User abc12345... fetching tiles
✅ Retrieved 5 tiles for user abc12345...
```

---

## Troubleshooting

### Issue: "Failed to insert tile record"

**Causes:**
- Database connection issue
- Invalid user_id (user doesn't exist in auth.users)
- RLS policies blocking insert

**Solution:**
1. Verify database connection
2. Ensure user is authenticated with valid token
3. Check Supabase logs for RLS policy violations

### Issue: "Not authenticated"

**Causes:**
- Missing Authorization header
- Invalid or expired JWT token
- Token from different Supabase project

**Solution:**
1. Verify token is included in Authorization header
2. Get a fresh token from frontend
3. Check token is from correct Supabase project

### Issue: Empty tiles array

**Possible reasons:**
- User hasn't added any tiles yet (normal)
- RLS policies filtering out tiles (check user_id matches)
- Database query error (check logs)

### Issue: "Tile not found or not owned by user" (DELETE)

**Causes:**
- Tile ID doesn't exist
- Tile belongs to a different user
- Tile was already deleted

**Solution:**
1. Verify the tile ID is correct
2. Check the tile belongs to the authenticated user
3. Refresh the tiles list before attempting delete

### Issue: Storage file not deleted

**Note:** This is expected behavior and not a failure

**Why:**
- Storage deletion is optional and graceful
- Database record is deleted even if storage deletion fails
- Prevents orphaned database records

---

## Summary

✅ **User-specific tile persistence** - Tiles linked to authenticated users
✅ **Cross-device sync** - Access tiles from any device
✅ **Survives page reloads** - Data persisted in Supabase
✅ **Secure by default** - RLS prevents unauthorized access
✅ **Full CRUD operations** - Create (POST), Read (GET), Delete (DELETE)
✅ **Automatic cleanup** - Storage files deleted with database records
✅ **Production-ready** - Comprehensive error handling and logging

Your tiles now persist across sessions with full management capabilities!
