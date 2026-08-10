"""Test package init.

Runs before any test submodule is imported, so it's the one place that's
guaranteed to win the race against import order: test files import
`backend.app` directly (or via `_asgi_client`) in whatever order unittest
discovers them, and `backend.app` reads LLM_PROVIDER from the environment at
import time. Force the deterministic DemoProvider here so a developer's local
.env (loaded by backend/db.py) can never make `python -m unittest` silently
place real LLM API calls. `setdefault` still lets an explicitly-exported env
var override this for a one-off manual run.
"""

import os

os.environ.setdefault("LLM_PROVIDER", "demo")
