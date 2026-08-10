"""PostgreSQL configuration and connection helpers."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

# Uvicorn does not load .env files automatically. Loading the repository-root
# file keeps `uvicorn backend.app:app` and `python -m backend.migrate` aligned.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def database_url() -> str | None:
    return os.getenv("DATABASE_URL")


def postgres_enabled() -> bool:
    return bool(database_url())


def connect(*, autocommit: bool = False) -> psycopg.Connection:
    """Open one PostgreSQL connection using the configured DATABASE_URL."""
    url = database_url()
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")
    return psycopg.connect(url, autocommit=autocommit, row_factory=dict_row)
