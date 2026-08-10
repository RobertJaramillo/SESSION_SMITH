"""PostgreSQL persistence for World Builder entries."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from backend.db import connect


class PostgresEntryRepository:
    def list(self, campaign_id: str) -> list[dict[str, Any]]:
        with connect() as connection:
            rows = connection.execute(
                """
                SELECT id, category, title, note, entry_tags
                FROM world_entries
                WHERE campaign_id = %s
                ORDER BY last_updated DESC, id DESC
                """,
                (campaign_id,),
            ).fetchall()
        return [{"id": row["id"], "category": row["category"], "title": row["title"], "note": row["note"], "tags": row["entry_tags"]} for row in rows]

    def create(self, campaign_id: str, *, category: str, title: str, note: str, tags: list[str]) -> dict[str, Any]:
        entry_id = f"entry_{uuid4().hex[:12]}"
        clean_tags = [tag.strip() for tag in tags if tag.strip()]
        with connect() as connection:
            row = connection.execute(
                """
                INSERT INTO world_entries (id, campaign_id, category, title, note, summary, entry_tags)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id, category, title, note, entry_tags
                """,
                (entry_id, campaign_id, category, title, note, title, Jsonb(clean_tags)),
            ).fetchone()
        return {"id": row["id"], "category": row["category"], "title": row["title"], "note": row["note"], "tags": row["entry_tags"]}
