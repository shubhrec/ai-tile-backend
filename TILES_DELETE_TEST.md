# Testing the DELETE Endpoint

Quick guide to test the new DELETE /api/tiles/{tile_id} endpoint.

## Prerequisites

1. Database migration completed (tiles table exists)
2. Backend server running: `uvicorn app.main:app --reload`
3. Valid JWT token from authenticated user

## Step-by-Step Test

### 1. Get Your JWT Token

In your frontend console:
```javascript
const { data } = await supabase.auth.getSession();
const token = data.session?.access_token;
console.log('Token:', token);
```

### 2. Add a Test Tile First

```bash
export TOKEN="your-jwt-token-here"

# Add a test tile
curl -X POST http://localhost:8000/api/tiles \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "image_url": "https://waqzrjsczmlvkapbkcno.supabase.co/storage/v1/object/public/tiles/test.jpg",
    "name": "Test Tile for Deletion"
  }'
```

Response:
```json
{
  "success": true,
  "tile": {
    "id": 1,
    "user_id": "...",
    "name": "Test Tile for Deletion",
    "image_url": "https://...",
    "created_at": "..."
  }
}
```

**Note the tile ID** (e.g., `id: 1`)

### 3. List Tiles to Verify

```bash
curl -X GET http://localhost:8000/api/tiles \
  -H "Authorization: Bearer $TOKEN"
```

You should see your test tile in the list.

### 4. Delete the Tile

```bash
# Replace 1 with your actual tile ID
curl -X DELETE http://localhost:8000/api/tiles/1 \
  -H "Authorization: Bearer $TOKEN"
```

Expected response:
```json
{
  "success": true,
  "deleted_id": 1
}
```

### 5. Verify Deletion

```bash
curl -X GET http://localhost:8000/api/tiles \
  -H "Authorization: Bearer $TOKEN"
```

The deleted tile should no longer appear in the list.

## Test Security Features

### Test 1: Delete Without Authentication

```bash
curl -X DELETE http://localhost:8000/api/tiles/1
```

Expected: `401 Unauthorized`

### Test 2: Delete Non-Existent Tile

```bash
curl -X DELETE http://localhost:8000/api/tiles/99999 \
  -H "Authorization: Bearer $TOKEN"
```

Expected: `404 Not Found` with message "Tile not found or not owned by user"

### Test 3: Delete Another User's Tile

1. Create a tile with User A
2. Try to delete it with User B's token

Expected: `404 Not Found` (RLS prevents seeing other users' tiles)

## Check Server Logs

When you delete a tile, you should see logs like:

```
🔐 User abc12345... attempting to delete tile ID=1
✅ Tile ID=1 deleted from database for user abc12345...
✅ File deleted from storage: tiles/test.jpg
```

Or if storage deletion fails:
```
🔐 User abc12345... attempting to delete tile ID=1
✅ Tile ID=1 deleted from database for user abc12345...
⚠️  Failed to delete file from storage: [error message]
```

Both are successful - storage deletion is optional.

## Verify in Supabase Dashboard

### Check Database

1. Go to Supabase Dashboard → Table Editor
2. Select `tiles` table
3. Verify the tile with the deleted ID is gone

### Check Storage (Optional)

1. Go to Supabase Dashboard → Storage
2. Navigate to `tiles` bucket
3. The associated image file should be deleted

## Integration Test Script

```bash
#!/bin/bash

# Set your token
TOKEN="your-jwt-token"

echo "1. Creating test tile..."
RESPONSE=$(curl -s -X POST http://localhost:8000/api/tiles \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"image_url": "https://example.com/test.jpg", "name": "Test"}')

TILE_ID=$(echo $RESPONSE | jq -r '.tile.id')
echo "Created tile with ID: $TILE_ID"

echo -e "\n2. Listing tiles..."
curl -s -X GET http://localhost:8000/api/tiles \
  -H "Authorization: Bearer $TOKEN" | jq '.tiles | length'

echo -e "\n3. Deleting tile $TILE_ID..."
curl -s -X DELETE http://localhost:8000/api/tiles/$TILE_ID \
  -H "Authorization: Bearer $TOKEN" | jq '.'

echo -e "\n4. Verifying deletion..."
curl -s -X GET http://localhost:8000/api/tiles \
  -H "Authorization: Bearer $TOKEN" | jq '.tiles | length'

echo -e "\nTest complete!"
```

## Expected Behavior Summary

✅ **DELETE with valid auth and ownership** → 200 OK, tile deleted
✅ **DELETE without auth** → 401 Unauthorized
✅ **DELETE non-existent tile** → 404 Not Found
✅ **DELETE other user's tile** → 404 Not Found (can't see it)
✅ **Storage file deleted automatically** → Best effort, won't fail request
✅ **Local state updated** → Frontend removes tile from UI

## Troubleshooting

### "Tile not found or not owned by user"

- Tile ID is wrong
- Tile belongs to different user
- Tile was already deleted

### Storage deletion warnings in logs

This is normal and expected. Storage deletion is optional and graceful. The database record is deleted successfully regardless.

### RLS Policy Issues

If you can't delete your own tiles, check:
```sql
-- Verify policies exist
SELECT * FROM pg_policies WHERE tablename = 'tiles';

-- Check user_id matches
SELECT id, user_id FROM tiles WHERE user_id = auth.uid();
```

## Success Criteria

- ✅ Can delete own tiles with valid auth
- ✅ Cannot delete without authentication
- ✅ Cannot delete other users' tiles
- ✅ Database record removed
- ✅ Storage file removed (best effort)
- ✅ Proper error messages
- ✅ Logging shows user and tile ID

All tests passing? You're good to go! 🎉
