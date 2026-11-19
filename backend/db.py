"""PostgreSQL configuration and connection helpers."""

from __future__ import annotations

import os
from contextlib import contextmanager
from functools import lru_cache
from threading import RLock
from psycopg_pool import ConnectionPool
from pathlib import Path

from dotenv import load_dotenv
from psycopg.rows import dict_row

# Uvicorn does not load .env files automatically. Loading the repository-root
# file keeps `uvicorn backend.app:app` and `python -m backend.migrate` aligned.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def database_url() -> str | None:
    return os.getenv("DATABASE_URL")


def postgres_enabled() -> bool:
    return bool(database_url())


_pool_lock = RLock()


@lru_cache(maxsize=4)
def _pool(url: str) -> ConnectionPool:
    return ConnectionPool(conninfo=url, min_size=0, max_size=8, timeout=15,
                          kwargs={'row_factory': dict_row, 'autocommit': True})


@contextmanager
def connect(*, autocommit: bool = False):
    """Lease a pooled connection; normal calls are one atomic transaction."""
    url = database_url()
    if not url:
        raise RuntimeError('DATABASE_URL is not configured')
    with _pool_lock:
        pool = _pool(url)
    with pool.connection() as connection:
        if autocommit:
            yield connection
        else:
            with connection.transaction():
                yield connection
