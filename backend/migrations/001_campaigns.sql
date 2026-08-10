CREATE TABLE campaigns (
    id                  text PRIMARY KEY,
    name                text NOT NULL,
    description         text NOT NULL DEFAULT '',
    system              text,
    status              text NOT NULL DEFAULT 'planning',
    tone                jsonb NOT NULL DEFAULT '[]'::jsonb,
    logline             text,
    role                text NOT NULL DEFAULT 'owner',
    visibility          text NOT NULL DEFAULT 'private',
    model_profile       text NOT NULL DEFAULT 'balanced',
    last_session_number integer NOT NULL DEFAULT 0,
    next_session_label  text NOT NULL DEFAULT 'Initial world setup incomplete',
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT campaigns_status_check CHECK (status IN ('active', 'planning', 'paused')),
    CONSTRAINT campaigns_role_check CHECK (role IN ('owner', 'gm', 'player', 'viewer')),
    CONSTRAINT campaigns_visibility_check CHECK (visibility IN ('private', 'shared')),
    CONSTRAINT campaigns_model_profile_check CHECK (model_profile IN ('cheap', 'balanced', 'premium'))
);

CREATE INDEX campaigns_updated_at_idx ON campaigns (updated_at DESC);
