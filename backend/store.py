"""
store.py — Postgres-backed storage layer for the AI worker pipeline.

This is what `backend.tools` (context.py, retrieval.py, storage.py, usage.py) means by
"the storage layer" — it assembles the `CampaignCorpus` retrieval reads from, and persists
the objects the worker produces (proposals, session preps, usage events).

Corpus loading only ever reads `sessions.summary`, never `session_notes.content` — the raw
note text never becomes part of the trusted corpus (AI_ARCHITECTURE.md §12.2, §13). Writes
for `memory_proposals`/`session_preps`/`usage_events` delegate to sibling methods on the
existing per-table repositories in `backend.repositories`, so each table's SQL still lives in
exactly one place.
"""

from __future__ import annotations

from backend.db import connect
from backend.rag import CampaignCorpus
from backend.repositories.jobs import PostgresJobRepository
from backend.repositories.proposals import PostgresProposalRepository
from backend.repositories.usage import PostgresUsageRepository
from backend.schemas import (
    Campaign,
    CanonEvent,
    Character,
    Faction,
    Location,
    MemoryProposal,
    Session,
    SessionPrep,
    StoryThread,
    UsageEvent,
    WorldEntry,
    WorldFramework,
)


class PostgresStore:
    def __init__(self) -> None:
        self._proposals = PostgresProposalRepository()
        self._jobs = PostgresJobRepository()
        self._usage = PostgresUsageRepository()

    def get_corpus(self, campaign_id: str) -> CampaignCorpus:
        with connect() as connection:
            campaign_row = connection.execute(
                "SELECT id, name, system, status, tone, logline, created_at FROM campaigns WHERE id = %s",
                (campaign_id,),
            ).fetchone()
            framework_row = connection.execute(
                """
                SELECT id, campaign_id, premise, tone, themes, constraints, starting_situation, updated_at
                FROM world_frameworks WHERE campaign_id = %s
                """,
                (campaign_id,),
            ).fetchone()
            # Loaded unfiltered; CampaignCorpus.trusted() is the single trust-boundary gate.
            # Nothing tags a world_entries row "approved_canon" yet (see WorldEntry.is_approved_canon),
            # so .trusted() zeroes this field today — that's the trust boundary working as intended,
            # not a gap this module needs to close.
            world_entry_rows = connection.execute(
                """
                SELECT id, campaign_id, category, note, summary, entry_tags, date_created, last_updated
                FROM world_entries WHERE campaign_id = %s
                """,
                (campaign_id,),
            ).fetchall()
            # These tables have no writer yet (no endpoint creates characters/factions/
            # locations/story_threads), so these always come back empty today. Querying
            # for real rather than hardcoding [] costs nothing and needs no changes here
            # once a writer exists.
            character_rows = connection.execute(
                """
                SELECT id, campaign_id, name, kind, ancestry, role, current_goal, summary, status, tags
                FROM characters WHERE campaign_id = %s
                """,
                (campaign_id,),
            ).fetchall()
            faction_rows = connection.execute(
                "SELECT id, campaign_id, name, summary, goals, status, tags FROM factions WHERE campaign_id = %s",
                (campaign_id,),
            ).fetchall()
            location_rows = connection.execute(
                "SELECT id, campaign_id, name, kind, summary, status, tags FROM locations WHERE campaign_id = %s",
                (campaign_id,),
            ).fetchall()
            thread_rows = connection.execute(
                """
                SELECT id, campaign_id, title, summary, status, priority, related_entity_ids
                FROM story_threads WHERE campaign_id = %s
                """,
                (campaign_id,),
            ).fetchall()
            session_rows = connection.execute(
                """
                SELECT id, campaign_id, session_number, title, played_at, status, summary, related_entry_ids
                FROM sessions WHERE campaign_id = %s
                """,
                (campaign_id,),
            ).fetchall()
            canon_rows = connection.execute(
                """
                SELECT id, campaign_id, summary, category, importance, related_entity_ids, source_note_ids,
                       source_proposal_id, status, model_provider, model_name, prompt_version,
                       created_by_job_id, schema_version, created_at
                FROM canon_events WHERE campaign_id = %s
                """,
                (campaign_id,),
            ).fetchall()

        return CampaignCorpus(
            campaign=Campaign(**campaign_row) if campaign_row else None,
            world_framework=WorldFramework(**framework_row) if framework_row else None,
            world_entries=[WorldEntry(**row) for row in world_entry_rows],
            characters=[Character(**row) for row in character_rows],
            factions=[Faction(**row) for row in faction_rows],
            locations=[Location(**row) for row in location_rows],
            story_threads=[StoryThread(**row) for row in thread_rows],
            canon_events=[CanonEvent(**row) for row in canon_rows],
            sessions=[Session(**row) for row in session_rows],
        )

    def save_proposal(self, proposal: MemoryProposal) -> MemoryProposal:
        self._proposals.insert_proposal(proposal)
        return proposal

    def save_session_prep(self, prep: SessionPrep) -> SessionPrep:
        self._jobs.insert_session_prep(prep)
        return prep

    def save_usage_event(self, event: UsageEvent) -> UsageEvent:
        self._usage.record(event)
        return event


_store: PostgresStore | None = None


def get_store() -> PostgresStore:
    global _store
    if _store is None:
        _store = PostgresStore()
    return _store
