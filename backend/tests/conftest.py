"""Keeps the backend test suite independent of the developer's local .env.

backend/auth.py gates /v1/* once GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET are
configured, and backend/db.py's load_dotenv() pulls those from the
repository-root .env the moment any backend module is imported. Without this,
a developer who has set up real Google OAuth for running the app locally
would find the test suite failing — the gate would be "on" during tests too.
Setting them to "" here (before backend.app and its dependents are first
imported) makes load_dotenv's default non-override behavior leave them
blank, so OAUTH_CONFIGURED is reliably False for every test run.
"""

import os

os.environ.setdefault("GOOGLE_CLIENT_ID", "")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "")
