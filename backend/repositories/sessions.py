"""Session and raw-note persistence."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from backend.db import connect


class PostgresSessionRepository:
    def create_note(self, campaign_id: str, *, content: str, session_number: str, title: str) -> tuple[str, str]:
        try:
            number = int(session_number)
        except ValueError as error:
            raise ValueError("sessionNumber must be an integer") from error
        if number < 0:
            raise ValueError("sessionNumber cannot be negative")

        session_id = f"session_{uuid4().hex[:12]}"
        note_id = f"note_{uuid4().hex[:12]}"
        with connect() as connection:
            session = connection.execute(
                """
                INSERT INTO sessions (id, campaign_id, session_number, title, status)
                VALUES (%s, %s, %s, %s, 'completed')
                ON CONFLICT (campaign_id, session_number)
                DO UPDATE SET title = EXCLUDED.title
                RETURNING id
                """,
                (session_id, campaign_id, number, title.strip() or None),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO session_notes (id, session_id, content)
                VALUES (%s, %s, %s)
                """,
                (note_id, session["id"], content),
            )
        return note_id, session["id"]

    def count(self, campaign_id: str) -> int:
        with connect() as connection:
            row = connection.execute("SELECT count(*) AS total FROM sessions WHERE campaign_id = %s", (campaign_id,)).fetchone()
        return int(row["total"])

    def recent_activity(self, campaign_id: str) -> list[dict[str, str]]:
        with connect() as connection:
            rows = connection.execute(
                """
                SELECT s.session_number, s.title
                FROM sessions AS s
                WHERE s.campaign_id = %s
                ORDER BY s.session_number DESC
                LIMIT 5
                """,
                (campaign_id,),
            ).fetchall()
        activity = []
        for row in rows:
            suffix = f" — {row['title']}" if row["title"] else ""
            activity.append({"actor": f"Session {row['session_number']}", "detail": f"Raw notes submitted{suffix}."})
        return activity
