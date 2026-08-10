-- Durable campaign-memory schema. Campaign shell columns live in 001_campaigns.sql.

CREATE TABLE world_frameworks (
    id                  text PRIMARY KEY,
    campaign_id         text NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    premise             text,
    tone                text,
    themes              jsonb NOT NULL DEFAULT '[]'::jsonb,
    constraints         jsonb NOT NULL DEFAULT '[]'::jsonb,
    starting_situation  text,
    updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE characters (
    id           text PRIMARY KEY,
    campaign_id  text NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    name         text NOT NULL,
    kind         text NOT NULL CHECK (kind IN ('pc', 'npc')),
    ancestry     text,
    role         text,
    current_goal text,
    summary      text,
    status       text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    tags         jsonb NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE factions (
    id          text PRIMARY KEY,
    campaign_id text NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    name        text NOT NULL,
    summary     text,
    goals       jsonb NOT NULL DEFAULT '[]'::jsonb,
    status      text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    tags        jsonb NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE locations (
    id          text PRIMARY KEY,
    campaign_id text NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    name        text NOT NULL,
    kind        text,
    summary     text,
    status      text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    tags        jsonb NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE story_threads (
    id                 text PRIMARY KEY,
    campaign_id        text NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    title              text NOT NULL,
    summary            text,
    status             text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved', 'paused', 'abandoned')),
    priority           text,
    related_entity_ids jsonb NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE world_entries (
    id           text PRIMARY KEY,
    campaign_id  text NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    category     text NOT NULL,
    title        text NOT NULL,
    note         text NOT NULL,
    summary      text,
    entry_tags   jsonb NOT NULL DEFAULT '[]'::jsonb,
    date_created timestamptz NOT NULL DEFAULT now(),
    last_updated timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE sessions (
    id                text PRIMARY KEY,
    campaign_id       text NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    session_number    integer NOT NULL,
    title             text,
    played_at         timestamptz,
    status            text NOT NULL DEFAULT 'planned' CHECK (status IN ('planned', 'completed', 'archived')),
    summary           text,
    related_entry_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    UNIQUE (campaign_id, session_number)
);

CREATE TABLE session_notes (
    id          text PRIMARY KEY,
    session_id  text NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    content     text NOT NULL,
    source_type text NOT NULL DEFAULT 'manual_notes',
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ai_jobs (
    id           text PRIMARY KEY,
    campaign_id  text REFERENCES campaigns(id) ON DELETE CASCADE,
    session_id   text REFERENCES sessions(id) ON DELETE SET NULL,
    job_type     text NOT NULL CHECK (job_type IN ('generate_session_prep', 'extract_memory', 'summarize_and_tag_session_entries')),
    status       text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'succeeded', 'failed', 'cancelled')),
    result       jsonb,
    error        text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);

CREATE TABLE memory_proposals (
    id                  text PRIMARY KEY,
    campaign_id         text NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    session_id          text REFERENCES sessions(id) ON DELETE SET NULL,
    source_note_id      text REFERENCES session_notes(id) ON DELETE SET NULL,
    type                text CHECK (type IN ('canon_event', 'character_update', 'faction_update', 'location_update', 'story_thread_update')),
    category            text,
    title               text,
    source              text,
    proposed_summary    text NOT NULL,
    proposed_payload    jsonb NOT NULL DEFAULT '{}'::jsonb,
    confidence          numeric(4,3),
    rationale           text,
    potential_conflicts jsonb NOT NULL DEFAULT '[]'::jsonb,
    status              text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'edited_approved', 'rejected', 'superseded')),
    reviewed_at         timestamptz,
    review_reason       text,
    model_provider      text,
    model_name          text,
    prompt_version      text,
    created_by_job_id   text REFERENCES ai_jobs(id) ON DELETE SET NULL,
    schema_version      text
);

CREATE TABLE canon_events (
    id                 text PRIMARY KEY,
    campaign_id        text NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    category           text,
    summary            text NOT NULL,
    importance         text CHECK (importance IN ('minor', 'normal', 'major', 'critical')),
    related_entity_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    source_note_ids    jsonb NOT NULL DEFAULT '[]'::jsonb,
    source_proposal_id text REFERENCES memory_proposals(id) ON DELETE SET NULL,
    status             text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revised', 'archived')),
    model_provider     text,
    model_name         text,
    prompt_version     text,
    created_by_job_id  text REFERENCES ai_jobs(id) ON DELETE SET NULL,
    schema_version     text,
    created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE session_preps (
    id                text PRIMARY KEY,
    campaign_id       text NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    session_id        text REFERENCES sessions(id) ON DELETE SET NULL,
    title             text,
    summary           text,
    sections          jsonb NOT NULL,
    source_memory_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    model_provider    text,
    model_name        text,
    prompt_version    text,
    created_by_job_id text REFERENCES ai_jobs(id) ON DELETE SET NULL,
    schema_version    text,
    created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE rag_chunks (
    id          text PRIMARY KEY,
    campaign_id text NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    category    text,
    entry_id    text,
    chunk_text  text NOT NULL,
    metadata    jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE usage_events (
    id                  text PRIMARY KEY,
    job_id              text REFERENCES ai_jobs(id) ON DELETE SET NULL,
    campaign_id         text REFERENCES campaigns(id) ON DELETE SET NULL,
    model_provider      text,
    model_name          text,
    prompt_version      text,
    input_tokens        integer,
    output_tokens       integer,
    estimated_cost_usd  numeric(10,4),
    latency_ms          integer,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX world_entries_campaign_category_idx ON world_entries (campaign_id, category);
CREATE INDEX world_entries_canon_tags_idx ON world_entries USING GIN (entry_tags);
CREATE INDEX sessions_campaign_number_idx ON sessions (campaign_id, session_number DESC);
CREATE INDEX session_notes_session_idx ON session_notes (session_id);
CREATE INDEX memory_proposals_review_queue_idx ON memory_proposals (campaign_id, status) WHERE status = 'pending';
CREATE INDEX canon_events_active_idx ON canon_events (campaign_id, status) WHERE status = 'active';
CREATE INDEX ai_jobs_pending_idx ON ai_jobs (created_at) WHERE status = 'pending';
CREATE INDEX rag_chunks_campaign_idx ON rag_chunks (campaign_id, category);
CREATE INDEX usage_events_campaign_idx ON usage_events (campaign_id, created_at DESC);
