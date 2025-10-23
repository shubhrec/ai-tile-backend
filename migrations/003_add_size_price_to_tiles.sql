-- Migration: Add size and price columns to tiles table
-- Description: Adds optional size and price fields for tile specifications
-- Author: System
-- Date: 2025-10-24

-- Add size column (optional string, max 50 chars)
ALTER TABLE tiles
ADD COLUMN IF NOT EXISTS size VARCHAR(50);

-- Add price column (optional numeric value)
ALTER TABLE tiles
ADD COLUMN IF NOT EXISTS price NUMERIC(10, 2);

-- Add comments to new columns
COMMENT ON COLUMN tiles.size IS 'Optional tile size specification (e.g., "600x600 mm")';
COMMENT ON COLUMN tiles.price IS 'Optional tile price (positive decimal value)';

-- Add check constraint to ensure price is positive if provided
ALTER TABLE tiles
ADD CONSTRAINT tiles_price_positive CHECK (price IS NULL OR price >= 0);
