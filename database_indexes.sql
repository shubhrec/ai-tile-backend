-- Database Performance Optimization Indexes
-- Run these SQL commands in your Supabase SQL Editor to improve query performance

-- ============================================================
-- CHATS TABLE INDEXES
-- ============================================================

-- Index for fetching user's chats ordered by creation date (most common query)
CREATE INDEX IF NOT EXISTS idx_chats_user_id_created_at
ON chats(user_id, created_at DESC);

-- ============================================================
-- TILES TABLE INDEXES
-- ============================================================

-- Index for fetching user's tiles ordered by creation date
CREATE INDEX IF NOT EXISTS idx_tiles_user_id_created_at
ON tiles(user_id, created_at DESC);

-- Index for filtering catalog tiles
CREATE INDEX IF NOT EXISTS idx_tiles_add_catalog
ON tiles(add_catalog)
WHERE add_catalog = true;

-- ============================================================
-- HOMES TABLE INDEXES
-- ============================================================

-- Index for fetching user's homes ordered by creation date
CREATE INDEX IF NOT EXISTS idx_homes_user_id_created_at
ON homes(user_id, created_at DESC);

-- ============================================================
-- GENERATED_IMAGES TABLE INDEXES
-- ============================================================

-- Index for fetching images by chat_id (used in chat detail view)
CREATE INDEX IF NOT EXISTS idx_generated_images_chat_id
ON generated_images(chat_id);

-- Index for fetching images by tile_id (used in tile detail view)
CREATE INDEX IF NOT EXISTS idx_generated_images_tile_id
ON generated_images(tile_id);

-- Index for fetching images by home_id (if queried)
CREATE INDEX IF NOT EXISTS idx_generated_images_home_id
ON generated_images(home_id);

-- Index for fetching user's generated images ordered by creation date
CREATE INDEX IF NOT EXISTS idx_generated_images_user_id_created_at
ON generated_images(user_id, created_at DESC);

-- Composite index for filtering by tile and user
CREATE INDEX IF NOT EXISTS idx_generated_images_tile_user
ON generated_images(tile_id, user_id);

-- Composite index for filtering by chat and user
CREATE INDEX IF NOT EXISTS idx_generated_images_chat_user
ON generated_images(chat_id, user_id);

-- ============================================================
-- VERIFICATION QUERIES
-- ============================================================
-- Run these to verify indexes were created successfully:

-- SELECT indexname, tablename
-- FROM pg_indexes
-- WHERE tablename IN ('chats', 'tiles', 'homes', 'generated_images')
-- ORDER BY tablename, indexname;
