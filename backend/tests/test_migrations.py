"""Lightweight guards for migration coverage when PostgreSQL is not running."""

from __future__ import annotations

from pathlib import Path


def test_campaign_memory_migration_contains_required_tables() -> None:
    sql = (Path(__file__).parents[1] / "migrations" / "002_campaign_memory.sql").read_text().lower()
    for table in (
        "world_entries",
        "sessions",
        "session_notes",
        "memory_proposals",
        "canon_events",
        "ai_jobs",
        "session_preps",
        "rag_chunks",
        "usage_events",
    ):
        assert f"create table {table}" in sql


def test_memory_proposals_are_not_canon_by_default() -> None:
    sql = (Path(__file__).parents[1] / "migrations" / "002_campaign_memory.sql").read_text().lower()
    assert "status              text not null default 'pending'" in sql


def test_canon_events_keep_a_category_column() -> None:
    """Approved canon must remember its proposal's category (see PostgresProposalRepository.review)."""
    sql = (Path(__file__).parents[1] / "migrations" / "002_campaign_memory.sql").read_text().lower()
    canon_events_block = sql.split("create table canon_events", 1)[1].split(");", 1)[0]
    assert "category" in canon_events_block
