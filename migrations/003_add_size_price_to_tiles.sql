-- Migration: Add size, price, and add_catalog columns to tiles table
-- Description: Adds optional size and price fields for tile specifications,
--              plus add_catalog flag to differentiate catalog tiles from temporary tiles
-- Author: System
-- Date: 2025-10-24

-- Add size column (optional string, max 50 chars)
ALTER TABLE tiles
ADD COLUMN IF NOT EXISTS size VARCHAR(50);

-- Add price column (optional numeric value)
ALTER TABLE tiles
ADD COLUMN IF NOT EXISTS price NUMERIC(10, 2);

-- Add add_catalog column (boolean, defaults to true)
ALTER TABLE tiles
ADD COLUMN IF NOT EXISTS add_catalog BOOLEAN DEFAULT TRUE;

-- Add comments to new columns
COMMENT ON COLUMN tiles.size IS 'Optional tile size specification (e.g., "600x600 mm")';
COMMENT ON COLUMN tiles.price IS 'Optional tile price (positive decimal value)';
COMMENT ON COLUMN tiles.add_catalog IS 'Flag indicating whether this tile should be in the catalog (true) or is temporary (false)';

-- Add check constraint to ensure price is positive if provided
ALTER TABLE tiles
ADD CONSTRAINT tiles_price_positive CHECK (price IS NULL OR price >= 0);
