"""Persist asynchronous API job state and generated prep drafts."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from backend.db import connect
from backend.schemas import SessionPrep


def _progress_from(status: str, result: dict[str, Any] | None) -> int:
    """0-100. Succeeded is always 100; while running/pending, derive it from
    categoriesCompleted/totalCategories when the caller has written partial
    world-build progress (see update_progress), else 0."""
    if status == "succeeded":
        return 100
    result = result or {}
    completed = result.get("categoriesCompleted")
    total = result.get("totalCategories")
    if completed is not None and total:
        return round(len(completed) / total * 100)
    return 0


class PostgresJobRepository:
    def create(self, campaign_id: str, *, job_type: str, session_id: str | None = None) -> str:
        job_id = f"job_{uuid4().hex[:12]}"
        with connect() as connection:
            connection.execute(
                "INSERT INTO ai_jobs (id, campaign_id, session_id, job_type) VALUES (%s, %s, %s, %s)",
                (job_id, campaign_id, session_id, job_type),
            )
        return job_id

    def get(self, job_id: str) -> dict[str, Any] | None:
        with connect() as connection:
            row = connection.execute(
                "SELECT id, job_type, status, result, error FROM ai_jobs WHERE id = %s", (job_id,)
            ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"], "type": row["job_type"], "status": row["status"],
            "progress": _progress_from(row["status"], row["result"]),
            "result": row["result"], "error": row["error"],
        }

    def list(self, campaign_id: str, *, job_type: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """Submission history for a campaign, newest first (session_number lets
        callers tell World Builder submissions, session 0, apart from regular
        session-notes jobs)."""
        with connect() as connection:
            rows = connection.execute(
                """
                SELECT j.id, j.job_type, j.status, j.result, j.error, j.created_at, s.session_number
                FROM ai_jobs AS j
                LEFT JOIN sessions AS s ON s.id = j.session_id
                WHERE j.campaign_id = %s AND (%s::text IS NULL OR j.job_type = %s)
                ORDER BY j.created_at DESC
                LIMIT %s
                """,
                (campaign_id, job_type, job_type, limit),
            ).fetchall()
        return [
            {
                "id": row["id"], "type": row["job_type"], "status": row["status"],
                "progress": _progress_from(row["status"], row["result"]),
                "result": row["result"], "error": row["error"],
                "sessionNumber": row["session_number"], "createdAt": row["created_at"].isoformat(),
            }
            for row in rows
        ]

    def update_progress(self, job_id: str, result: dict[str, Any]) -> None:
        """Write partial progress while the job is still in flight (does not
        complete it). Flips pending -> running so callers can tell 'not started
        yet' apart from 'working, here is what's done so far'."""
        with connect() as connection:
            connection.execute(
                "UPDATE ai_jobs SET status = CASE WHEN status = 'pending' THEN 'running' ELSE status END, result = %s WHERE id = %s",
                (Jsonb(result), job_id),
            )

    def complete(self, job_id: str, result: dict[str, Any]) -> None:
        with connect() as connection:
            connection.execute(
                "UPDATE ai_jobs SET status = 'succeeded', result = %s, completed_at = now() WHERE id = %s",
                (Jsonb(result), job_id),
            )

    def fail(self, job_id: str, error: str) -> None:
        with connect() as connection:
            connection.execute(
                "UPDATE ai_jobs SET status = 'failed', error = %s, completed_at = now() WHERE id = %s",
                (error, job_id),
            )

    def insert_session_prep(self, prep: SessionPrep) -> None:
        with connect() as connection:
            connection.execute(
                """
                INSERT INTO session_preps (
                    id, campaign_id, session_id, title, summary, sections, source_memory_ids,
                    model_provider, model_name, prompt_version, created_by_job_id, schema_version
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    prep.id, prep.campaign_id, prep.session_id, prep.title, prep.summary,
                    Jsonb(prep.sections.model_dump(mode="json")), Jsonb(prep.source_memory_ids),
                    prep.model_provider, prep.model_name, prep.prompt_version,
                    prep.created_by_job_id, prep.schema_version,
                ),
            )

    def get_latest_prep(self, campaign_id: str) -> dict[str, Any] | None:
        """Most recent prep for a campaign, draft or approved — for restoring the
        Session Prep page on load."""
        with connect() as connection:
            row = connection.execute(
                """
                SELECT id, title, summary, sections, status, approved_outline
                FROM session_preps WHERE campaign_id = %s
                ORDER BY created_at DESC LIMIT 1
                """,
                (campaign_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_latest_approved_prep(self, campaign_id: str) -> dict[str, Any] | None:
        """Most recently APPROVED prep — what the world export surfaces as the
        (non-canon) plan for next session."""
        with connect() as connection:
            row = connection.execute(
                """
                SELECT id, title, summary, sections, approved_outline, approved_at
                FROM session_preps WHERE campaign_id = %s AND status = 'approved'
                ORDER BY approved_at DESC LIMIT 1
                """,
                (campaign_id,),
            ).fetchone()
        return dict(row) if row else None

    def approve_prep(self, prep_id: str, campaign_id: str, outline: str) -> dict[str, Any] | None:
        """Mark a prep as the GM-approved plan for next session, storing the GM's
        (possibly edited) outline text. Re-approving (e.g. after further edits)
        just updates the stored text and timestamp."""
        with connect() as connection:
            row = connection.execute(
                """
                UPDATE session_preps SET status = 'approved', approved_outline = %s, approved_at = now()
                WHERE id = %s AND campaign_id = %s
                RETURNING id, title, summary, sections, status, approved_outline
                """,
                (outline, prep_id, campaign_id),
            ).fetchone()
        return dict(row) if row else None
