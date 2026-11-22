CREATE TABLE google_identities (
    subject text PRIMARY KEY,
    user_id text NOT NULL REFERENCES app_users(id) ON DELETE CASCADE
);
