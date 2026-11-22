CREATE TABLE firebase_identities (
    uid text PRIMARY KEY,
    user_id text NOT NULL UNIQUE REFERENCES app_users(id) ON DELETE CASCADE
);
