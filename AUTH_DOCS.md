# Authentication & Authorization Documentation

## Overview

The backend now implements secure JWT-based authentication using Supabase Auth. All sensitive endpoints require a valid Bearer token, and user IDs are automatically extracted and linked to generated content.

---

## Setup

### 1. Install Dependencies

PyJWT and requests are now included in `requirements.txt`:

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

**No manual JWT configuration needed!**

The system automatically fetches public keys from Supabase's JWKS endpoint:
```
https://waqzrjsczmlvkapbkcno.supabase.co/auth/v1/.well-known/jwks.json
```

Keys are cached for 10 minutes and automatically rotated when Supabase updates them.

Only required environment variables:
```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key-here
```

---

## Architecture

### New Files

1. **`app/services/auth.py`**
   - JWT verification functions
   - User authentication middleware
   - Admin role checking

2. **Updated Routes:**
   - `app/api/routes_generate.py` - Protected with auth
   - `app/api/routes_uploads.py` - Protected with auth

---

## How Authentication Works

### 1. Frontend Login

User logs in via Supabase Auth (handled by frontend):

```typescript
const { data, error } = await supabase.auth.signInWithPassword({
  email: user@example.com',
  password: 'password123'
});

const token = data.session?.access_token;
```

### 2. Include Token in Requests

Frontend sends token in Authorization header:

```typescript
const response = await fetch('http://localhost:8000/generate', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({ tile_url, home_url, prompt })
});
```

### 3. Backend Verification

Backend verifies JWT using JWKS and extracts user ID:

```python
# In verify_token() function:
# 1. Extract 'kid' (key ID) from token header
unverified_header = jwt.get_unverified_header(token)
kid = unverified_header.get("kid")

# 2. Fetch JWKS from Supabase (cached for 10 minutes)
jwks = _get_jwks()

# 3. Find matching public key
key = next((k for k in jwks if k["kid"] == kid), None)

# 4. Verify token with ES256 algorithm
public_key = ECAlgorithm.from_jwk(key)
payload = jwt.decode(token, public_key, algorithms=["ES256"], audience="authenticated")

# 5. Extract and attach user ID
user_id = payload.get("sub")
request.state.user_id = user_id
```

### 4. Automatic User Linking

Protected endpoints automatically have access to `user_id`:

```python
@router.post("/generate", dependencies=[Depends(verify_token)])
async def generate_image(request: Request, body: GenerateRequest):
    user_id = request.state.user_id  # Extracted from JWT

    # Link to database record
    db_record = {
        "user_id": user_id,
        "prompt": body.prompt,
        "image_url": public_url
    }
```

---

## Protected Endpoints

### POST /generate

**Authentication:** Required ✅

**Request:**
```bash
curl -X POST http://localhost:8000/generate \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tile_url": "https://example.com/tile.jpg",
    "home_url": "https://example.com/room.jpg",
    "prompt": "modern bathroom"
  }'
```

**Response:**
```json
{
  "success": true,
  "image_url": "https://...supabase.co/storage/v1/object/public/generated/..."
}
```

**Database Record:**
```json
{
  "user_id": "user-uuid-from-jwt",
  "tile_id": null,
  "prompt": "modern bathroom",
  "image_url": "https://..."
}
```

---

### POST /api/upload/{bucket}

**Authentication:** Required ✅

**Request:**
```bash
curl -X POST http://localhost:8000/api/upload/tiles \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -F "file=@tile.jpg"
```

**Response:**
```json
{
  "success": true,
  "url": "https://...supabase.co/storage/v1/object/public/tiles/1732189234_tile.jpg"
}
```

**Logs:**
```
🔐 User abc12345... uploading to bucket 'tiles'
✅ File uploaded by abc12345...: 1732189234_tile.jpg to bucket 'tiles'
```

---

### GET /api/list/{bucket}

**Authentication:** Optional (public for now)

Can be protected by adding `dependencies=[Depends(verify_token)]` if needed.

---

## Authentication Functions

### `verify_token(request: Request) -> str`

**Purpose:** Verify JWT and attach user_id to request

**Usage:**
```python
@router.post("/endpoint", dependencies=[Depends(verify_token)])
async def my_endpoint(request: Request):
    user_id = request.state.user_id
```

**Raises:**
- `401 Unauthorized` - Missing, invalid, or expired token
- `500 Internal Server Error` - JWT key not configured

---

### `get_optional_user_id(request: Request) -> Optional[str]`

**Purpose:** Extract user_id if authenticated, otherwise return None

**Usage:**
```python
@router.get("/public-endpoint")
async def public_endpoint(request: Request):
    user_id = get_optional_user_id(request)
    if user_id:
        # Personalized response for authenticated users
    else:
        # Public response
```

---

### `require_admin(request: Request) -> str`

**Purpose:** Verify token and check for admin role

**Usage:**
```python
@router.delete("/admin/delete-user", dependencies=[Depends(require_admin)])
async def delete_user(request: Request, user_id: str):
    admin_id = request.state.user_id
    # Admin-only operations
```

**Raises:**
- `401 Unauthorized` - Invalid token
- `403 Forbidden` - User is not an admin

---

## Error Responses

### 401 Unauthorized

**Missing Token:**
```json
{
  "detail": "Missing Authorization header. Please provide a valid JWT token."
}
```

**Invalid Format:**
```json
{
  "detail": "Invalid Authorization header format. Use 'Bearer <token>'."
}
```

**Expired Token:**
```json
{
  "detail": "Token has expired. Please log in again."
}
```

**Invalid Token:**
```json
{
  "detail": "Invalid token: Signature verification failed"
}
```

### 403 Forbidden

**Admin Required:**
```json
{
  "detail": "Admin access required"
}
```

### 500 Internal Server Error

**Missing Configuration:**
```json
{
  "detail": "Authentication service not configured properly"
}
```

---

## Frontend Integration

### React/Next.js Example

```typescript
// lib/api.ts
import { createClient } from '@supabase/supabase-js';

const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

async function getAuthToken(): Promise<string | null> {
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token || null;
}

export async function generateImage(
  tileUrl: string,
  homeUrl: string,
  prompt: string
) {
  const token = await getAuthToken();

  if (!token) {
    throw new Error('User not authenticated');
  }

  const response = await fetch('http://localhost:8000/generate', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      tile_url: tileUrl,
      home_url: homeUrl,
      prompt: prompt,
    }),
  });

  if (response.status === 401) {
    throw new Error('Authentication failed. Please log in again.');
  }

  return response.json();
}

export async function uploadTile(file: File) {
  const token = await getAuthToken();

  if (!token) {
    throw new Error('User not authenticated');
  }

  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch('http://localhost:8000/api/upload/tiles', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
    },
    body: formData,
  });

  return response.json();
}
```

### React Component Example

```typescript
// components/TileGenerator.tsx
import { useState } from 'react';
import { generateImage } from '@/lib/api';

export function TileGenerator() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleGenerate = async () => {
    try {
      setLoading(true);
      setError(null);

      const result = await generateImage(
        'https://example.com/tile.jpg',
        'https://example.com/room.jpg',
        'modern bathroom'
      );

      if (result.success) {
        console.log('Generated image:', result.image_url);
      } else {
        setError(result.error);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <button onClick={handleGenerate} disabled={loading}>
        {loading ? 'Generating...' : 'Generate Visualization'}
      </button>
      {error && <p className="error">{error}</p>}
    </div>
  );
}
```

---

## Testing

### 1. Get a Test Token

Login via frontend and copy the JWT:

```typescript
const { data } = await supabase.auth.getSession();
console.log(data.session?.access_token);
```

Or use Supabase CLI:

```bash
supabase auth login
```

### 2. Test with cURL

```bash
# Set token variable
export TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

# Test generate endpoint
curl -X POST http://localhost:8000/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tile_url": "https://example.com/tile.jpg",
    "home_url": "https://example.com/room.jpg",
    "prompt": "test"
  }'

# Test upload endpoint
curl -X POST http://localhost:8000/api/upload/tiles \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@test.jpg"
```

### 3. Test Invalid Token

```bash
# No token
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{"tile_url":"...","home_url":"..."}'

# Response: 401 Unauthorized

# Invalid token
curl -X POST http://localhost:8000/generate \
  -H "Authorization: Bearer invalid-token" \
  -H "Content-Type: application/json" \
  -d '{"tile_url":"...","home_url":"..."}'

# Response: 401 Unauthorized
```

---

## Logging

All authentication events are logged:

```
✅ User authenticated: abc12345...
🔐 Authenticated user: abc12345...
✅ Database record inserted for user abc12345...: [...]
🔐 User abc12345... uploading to bucket 'tiles'
✅ File uploaded by abc12345...: 1732189234_tile.jpg
```

View logs:

```bash
uvicorn app.main:app --reload --log-level info
```

---

## Security Best Practices

### Backend

✅ **JWKS auto-rotation** - No manual key management required
✅ **Validate all tokens** - Use `dependencies=[Depends(verify_token)]`
✅ **Log auth events** - Track who's accessing what
✅ **Use HTTPS in production** - Never send JWTs over HTTP
✅ **ES256 algorithm** - More secure than HS256
✅ **Audience verification** - Ensures tokens are for your app

### Frontend

✅ **Store tokens securely** - Use httpOnly cookies when possible
✅ **Refresh tokens automatically** - Before expiry
✅ **Clear tokens on logout** - Prevent reuse
✅ **Handle 401 gracefully** - Redirect to login
✅ **Never log tokens** - Avoid console.log with tokens

---

## Troubleshooting

### Issue: "Failed to fetch JWKS"

**Causes:**
- Network connectivity issues
- Supabase endpoint is down
- Firewall blocking requests

**Solution:**
1. Check network connectivity
2. Verify Supabase project is active
3. Check server can reach external URLs

### Issue: "Invalid token: Signature verification failed"

**Causes:**
- Token from different Supabase project
- Token manually modified
- JWKS cache out of sync (rare)

**Solution:**
- Verify token is from correct Supabase project
- Get a fresh token from frontend
- Wait 10 minutes for JWKS cache to refresh

### Issue: "Token has expired"

**Solution:**
- Frontend should refresh token automatically
- If manual testing, get a new token

### Issue: User ID not showing in database

**Check:**
1. Endpoint has `dependencies=[Depends(verify_token)]`
2. Using `request.state.user_id` correctly
3. Token contains `sub` claim

---

## Database Schema

Ensure your `generated_images` table has `user_id` column:

```sql
CREATE TABLE generated_images (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  tile_id TEXT,
  prompt TEXT NOT NULL,
  image_url TEXT NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Add index for faster user queries
CREATE INDEX idx_generated_images_user_id ON generated_images(user_id);

-- Row Level Security (optional but recommended)
ALTER TABLE generated_images ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own images"
  ON generated_images FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own images"
  ON generated_images FOR INSERT
  WITH CHECK (auth.uid() = user_id);
```

---

## Next Steps

### Extend Authentication

1. **Add role-based access:**
   ```python
   @router.delete("/admin/content", dependencies=[Depends(require_admin)])
   ```

2. **Add user-specific endpoints:**
   ```python
   @router.get("/my-images")
   async def get_my_images(request: Request):
       user_id = request.state.user_id
       # Query images for this user only
   ```

3. **Add rate limiting:**
   ```python
   from slowapi import Limiter
   limiter.limit("10/minute")(generate_image)
   ```

4. **Add audit logging:**
   ```python
   await log_user_action(user_id, "generate_image", metadata)
   ```

---

## Summary

✅ **JWKS-based JWT verification** - Automatic key rotation, no manual config
✅ **ES256 algorithm** - Industry-standard elliptic curve signature
✅ **Protected endpoints** - `/generate` and `/api/upload`
✅ **Automatic user linking** - User IDs attached to all content
✅ **Comprehensive logging** - Track all auth events
✅ **Error handling** - Standardized 401/403 responses
✅ **Frontend integration** - Ready for React/Next.js
✅ **Admin support** - Role-based access control ready
✅ **Zero maintenance** - Keys automatically update from Supabase

All sensitive operations now require authentication, and user IDs are automatically tracked!
