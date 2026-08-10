-- Session prep approval lifecycle: a generated prep is a draft until the GM
-- explicitly approves it as the plan for next session. Approved preps are NOT
-- canon (they aren't derived from session notes or approved world-building) —
-- they're surfaced in the world export as a separate, clearly-labeled section.
ALTER TABLE session_preps ADD COLUMN status text NOT NULL DEFAULT 'draft'
    CHECK (status IN ('draft', 'approved'));
ALTER TABLE session_preps ADD COLUMN approved_outline text;
ALTER TABLE session_preps ADD COLUMN approved_at timestamptz;
