"""Proposal review queue and approved-canon persistence."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from backend.db import connect
from backend.schemas import MemoryProposal, classify_canon_origin


def _confidence_label(value: float | None) -> str:
    if value is None or value < 0.5:
        return "Low"
    if value < 0.8:
        return "Medium"
    return "High"


def _title_from_summary(summary: str) -> str:
    """Derive a short display title from a proposal summary."""
    first = (summary or "").strip().split(". ")[0].strip()
    return first[:80].rstrip(".") if len(first) >= 8 else "Campaign update"


class PostgresProposalRepository:
    def pending_count(self, campaign_id: str) -> int:
        with connect() as connection:
            row = connection.execute("SELECT count(*) AS total FROM memory_proposals WHERE campaign_id = %s AND status = 'pending'", (campaign_id,)).fetchone()
        return int(row["total"])

    def canon_count(self, campaign_id: str) -> int:
        with connect() as connection:
            row = connection.execute("SELECT count(*) AS total FROM canon_events WHERE campaign_id = %s AND status = 'active'", (campaign_id,)).fetchone()
        return int(row["total"])

    def list(self, campaign_id: str, proposal_status: str | None) -> list[dict[str, Any]]:
        query = """
            SELECT id, title, category, confidence, proposed_summary, source, status, potential_conflicts
            FROM memory_proposals WHERE campaign_id = %s
        """
        params: list[str] = [campaign_id]
        if proposal_status:
            query += " AND status = %s"
            params.append(proposal_status)
        query += " ORDER BY id DESC"
        with connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [
            {
                "id": row["id"],
                "title": row["title"] or "Campaign update",
                "category": row["category"] or "General Overview",
                "confidence": _confidence_label(float(row["confidence"]) if row["confidence"] is not None else None),
                "summary": row["proposed_summary"],
                "source": row["source"] or None,
                "status": row["status"],
                "conflicts": row["potential_conflicts"] or [],
            }
            for row in rows
        ]

    def insert_proposal(self, proposal: MemoryProposal) -> None:
        category, title = proposal.category.value, _title_from_summary(proposal.proposed_summary)
        with connect() as connection:
            connection.execute(
                """
                INSERT INTO memory_proposals (
                    id, campaign_id, session_id, source_note_id, type, category, title,
                    proposed_summary, proposed_payload, confidence, rationale, potential_conflicts, status,
                    model_provider, model_name, prompt_version, created_by_job_id, schema_version
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    proposal.id, proposal.campaign_id, proposal.session_id, proposal.source_note_id,
                    proposal.type.value if proposal.type else None, category, title,
                    proposal.proposed_summary,
                    Jsonb(proposal.proposed_payload), proposal.confidence, proposal.rationale,
                    Jsonb(proposal.potential_conflicts), proposal.status.value,
                    proposal.model_provider, proposal.model_name, proposal.prompt_version,
                    proposal.created_by_job_id, proposal.schema_version,
                ),
            )

    def list_canon(self, campaign_id: str) -> list[dict[str, str]]:
        # ASC (oldest first): a canon document reads as a coherent history when
        # entries appear in the order things actually happened. Matches the
        # in-memory backend, which is already chronological (state["canon"] is
        # built via .append()) — the two backends previously disagreed on order.
        with connect() as connection:
            rows = connection.execute(
                """
                SELECT id, category, summary, prompt_version
                FROM canon_events WHERE campaign_id = %s AND status = 'active' ORDER BY created_at ASC
                """,
                (campaign_id,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "category": row["category"] or "General Overview",
                "summary": row["summary"],
                "origin": classify_canon_origin(row["prompt_version"]),
            }
            for row in rows
        ]

    def reject_all_pending(self, campaign_id: str) -> int:
        """Reject every pending proposal for a campaign (used by Regenerate so a
        rebuild replaces the prior draft instead of piling up). Approved canon is
        untouched. Returns how many were rejected."""
        with connect() as connection:
            result = connection.execute(
                "UPDATE memory_proposals SET status = 'rejected', reviewed_at = now(), review_reason = 'superseded by rebuild' WHERE campaign_id = %s AND status = 'pending'",
                (campaign_id,),
            )
            return result.rowcount

    def review(self, proposal_id: str, *, action: str, edited_summary: str | None, reason: str | None) -> dict[str, Any] | None:
        with connect() as connection:
            proposal = connection.execute(
                """
                SELECT id, campaign_id, category, proposed_summary, status,
                       model_provider, model_name, prompt_version, created_by_job_id, schema_version
                FROM memory_proposals WHERE id = %s FOR UPDATE
                """,
                (proposal_id,),
            ).fetchone()
            if not proposal:
                return None
            if proposal["status"] != "pending":
                raise ValueError("proposal_already_reviewed")
            if action == "reject":
                connection.execute(
                    "UPDATE memory_proposals SET status = 'rejected', reviewed_at = now(), review_reason = %s WHERE id = %s",
                    (reason, proposal_id),
                )
                return {"proposalId": proposal_id, "status": "rejected", "createdCanonId": None}

            summary = edited_summary if action == "edit_approve" else proposal["proposed_summary"]
            if not summary:
                raise ValueError("missing_edited_summary")
            next_status = "edited_approved" if action == "edit_approve" else "approved"
            canon_id = f"canon_{uuid4().hex[:12]}"
            connection.execute(
                "UPDATE memory_proposals SET status = %s, proposed_summary = %s, reviewed_at = now() WHERE id = %s",
                (next_status, summary, proposal_id),
            )
            connection.execute(
                """
                INSERT INTO canon_events (
                    id, campaign_id, category, summary, source_proposal_id,
                    model_provider, model_name, prompt_version, created_by_job_id, schema_version
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    canon_id, proposal["campaign_id"], proposal["category"], summary, proposal_id,
                    proposal["model_provider"], proposal["model_name"], proposal["prompt_version"],
                    proposal["created_by_job_id"], proposal["schema_version"],
                ),
            )
        return {"proposalId": proposal_id, "status": next_status, "createdCanonId": canon_id}
