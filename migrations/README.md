# Database Migrations

This directory contains SQL migration scripts for the Tiles application database.

## How to Run Migrations

### Option 1: Supabase Dashboard (Recommended)

1. Go to your Supabase project dashboard
2. Navigate to: **SQL Editor**
3. Click **New Query**
4. Copy and paste the contents of the migration file
5. Click **Run** to execute

### Option 2: Supabase CLI

```bash
# Install Supabase CLI (if not already installed)
npm install -g supabase

# Login to Supabase
supabase login

# Link to your project
supabase link --project-ref waqzrjsczmlvkapbkcno

# Run migration
supabase db push migrations/001_create_tiles_table.sql
```

### Option 3: Manual psql

```bash
psql -h db.waqzrjsczmlvkapbkcno.supabase.co \
     -U postgres \
     -d postgres \
     -f migrations/001_create_tiles_table.sql
```

## Migration Files

### 001_create_tiles_table.sql

Creates the `tiles` table with the following features:

**Schema:**
- `id` - Auto-incrementing primary key
- `user_id` - Foreign key to auth.users (required)
- `name` - Optional tile name/description
- `image_url` - Supabase Storage URL (required)
- `created_at` - Timestamp (auto-generated)

**Security:**
- Row Level Security (RLS) enabled
- Users can only view/insert/update/delete their own tiles
- Cascading delete when user is removed

**Performance:**
- Index on `user_id` for fast user-specific queries
- Index on `created_at` for efficient ordering

## Verification

After running the migration, verify it worked:

```sql
-- Check table exists
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name = 'tiles';

-- Check RLS is enabled
SELECT tablename, rowsecurity
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename = 'tiles';

-- Check policies exist
SELECT policyname, cmd
FROM pg_policies
WHERE tablename = 'tiles';
```

## Testing

Test the table with some sample data:

```sql
-- Insert test tile (replace with real user_id from auth.users)
INSERT INTO tiles (user_id, name, image_url)
VALUES (
    'your-user-uuid-here',
    'Modern Bathroom Tile',
    'https://waqzrjsczmlvkapbkcno.supabase.co/storage/v1/object/public/tiles/example.jpg'
);

-- Query tiles for a user
SELECT * FROM tiles
WHERE user_id = 'your-user-uuid-here'
ORDER BY created_at DESC;
```

## Rollback

If you need to undo this migration:

```sql
-- Drop policies
DROP POLICY IF EXISTS "Users can view own tiles" ON tiles;
DROP POLICY IF EXISTS "Users can insert own tiles" ON tiles;
DROP POLICY IF EXISTS "Users can update own tiles" ON tiles;
DROP POLICY IF EXISTS "Users can delete own tiles" ON tiles;

-- Drop indexes
DROP INDEX IF EXISTS idx_tiles_user_id;
DROP INDEX IF EXISTS idx_tiles_created_at;

-- Drop table
DROP TABLE IF EXISTS tiles;
```
