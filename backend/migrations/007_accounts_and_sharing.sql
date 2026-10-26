CREATE TABLE app_users (
    id text PRIMARY KEY, email text NOT NULL UNIQUE, name text NOT NULL,
    password_hash text NOT NULL
);
CREATE TABLE account_sessions (
    token_hash text PRIMARY KEY, user_id text NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    expires_at double precision NOT NULL
);
CREATE TABLE friendships (
    id text PRIMARY KEY, sender_id text NOT NULL REFERENCES app_users(id),
    recipient_id text NOT NULL REFERENCES app_users(id), status text NOT NULL CHECK(status IN ('pending','accepted')),
    pair_key text NOT NULL UNIQUE, CHECK(sender_id <> recipient_id)
);
CREATE TABLE campaign_access (
    campaign_id text NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    user_id text NOT NULL REFERENCES app_users(id), role text NOT NULL CHECK(role IN ('owner','player','viewer')),
    PRIMARY KEY(campaign_id,user_id)
);
CREATE UNIQUE INDEX campaign_one_owner ON campaign_access(campaign_id) WHERE role = 'owner';
CREATE TABLE campaign_invitations (
    id text PRIMARY KEY, campaign_id text NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    sender_id text NOT NULL REFERENCES app_users(id), email text NOT NULL,
    role text NOT NULL CHECK(role IN ('player','viewer')),
    expires_at double precision NOT NULL,
    UNIQUE(campaign_id,email)
);
CREATE INDEX account_sessions_expiry ON account_sessions(expires_at);
CREATE INDEX campaign_access_user ON campaign_access(user_id);
