-- World-building lifecycle: a campaign's world is built once ('draft'), then
-- 'sealed'. While draft the World Builder is editable; once sealed it is
-- read-only and all further change flows through session notes (extract_memory).
ALTER TABLE campaigns ADD COLUMN world_status text NOT NULL DEFAULT 'draft'
    CHECK (world_status IN ('draft', 'sealed'));

-- Existing campaigns that have already been played have a built world.
UPDATE campaigns SET world_status = 'sealed' WHERE last_session_number > 0;
