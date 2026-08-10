"""Postgres-backed regression test for the memory-proposal review lifecycle.

Skipped unless DATABASE_URL is configured (see backend/db.py); the contract
smoke tests in test_api.py force the in-memory repository and can't reach
this code path, which previously dropped the canon event's category.
"""

from __future__ import annotations

import time
import unittest
from uuid import uuid4

from backend.db import connect, postgres_enabled
from backend.migrate import apply_migrations
from backend.repositories.campaigns import PostgresCampaignRepository
from backend.repositories.proposals import PostgresProposalRepository


@unittest.skipUnless(postgres_enabled(), "DATABASE_URL is not configured")
class ProposalReviewCategoryTests(unittest.TestCase):
    def setUp(self) -> None:
        apply_migrations()
        self.campaigns = PostgresCampaignRepository()
        self.proposals = PostgresProposalRepository()
        campaign = self.campaigns.create(name="Category regression test", description="")
        self.campaign_id = campaign["campaignId"]

    def tearDown(self) -> None:
        with connect(autocommit=True) as connection:
            connection.execute("DELETE FROM campaigns WHERE id = %s", (self.campaign_id,))

    def test_approving_a_proposal_preserves_its_category(self) -> None:
        proposal_id = f"proposal_{uuid4().hex[:12]}"
        with connect() as connection:
            connection.execute(
                """
                INSERT INTO memory_proposals (id, campaign_id, title, category, proposed_summary)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (proposal_id, self.campaign_id, "Oath law tightens", "Magic Systems", "Binding oaths now require a blood price."),
            )

        result = self.proposals.review(proposal_id, action="approve", edited_summary=None, reason=None)
        self.assertIsNotNone(result)
        canon_id = result["createdCanonId"]

        canon = self.proposals.list_canon(self.campaign_id)
        matching = next(item for item in canon if item["id"] == canon_id)
        self.assertEqual(matching["category"], "Magic Systems")

    def test_approving_a_proposal_carries_prompt_version_into_canon_origin(self) -> None:
        """Regression test for the eval-scoping bug: canon_events has always had
        a prompt_version column, but review() never copied it from the source
        proposal, so nothing could distinguish faithful note-extraction canon
        from deliberately creative World-Builder canon (see KNOWN_LIMITATIONS.md)."""
        note_proposal_id = f"proposal_{uuid4().hex[:12]}"
        world_proposal_id = f"proposal_{uuid4().hex[:12]}"
        with connect() as connection:
            connection.execute(
                """
                INSERT INTO memory_proposals (id, campaign_id, title, category, proposed_summary, prompt_version)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (note_proposal_id, self.campaign_id, "Tithe increase", "Economy", "Grain tithes doubled.", "note_extraction.v1"),
            )
            connection.execute(
                """
                INSERT INTO memory_proposals (id, campaign_id, title, category, proposed_summary, prompt_version)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (world_proposal_id, self.campaign_id, "Invented race", "Races", "The Sylvan Kin walk the vale.", "world_expand.v1"),
            )

        note_result = self.proposals.review(note_proposal_id, action="approve", edited_summary=None, reason=None)
        world_result = self.proposals.review(world_proposal_id, action="approve", edited_summary=None, reason=None)

        canon = self.proposals.list_canon(self.campaign_id)
        note_canon = next(item for item in canon if item["id"] == note_result["createdCanonId"])
        world_canon = next(item for item in canon if item["id"] == world_result["createdCanonId"])
        self.assertEqual(note_canon["origin"], "session_notes")
        self.assertEqual(world_canon["origin"], "world_builder")

    def test_list_canon_returns_oldest_first(self) -> None:
        """A world-export reads as a coherent history only if entries appear in
        the order things happened. list_canon() previously returned newest-first
        (ORDER BY created_at DESC), backwards relative to the in-memory backend
        and to how build_world_export_markdown groups/renders canon."""
        first_id = f"proposal_{uuid4().hex[:12]}"
        second_id = f"proposal_{uuid4().hex[:12]}"
        with connect() as connection:
            connection.execute(
                "INSERT INTO memory_proposals (id, campaign_id, title, category, proposed_summary) VALUES (%s, %s, %s, %s, %s)",
                (first_id, self.campaign_id, "First event", "Economy", "The toll office opened."),
            )
        first_result = self.proposals.review(first_id, action="approve", edited_summary=None, reason=None)
        time.sleep(0.01)  # guarantee a distinct created_at from the first insert
        with connect() as connection:
            connection.execute(
                "INSERT INTO memory_proposals (id, campaign_id, title, category, proposed_summary) VALUES (%s, %s, %s, %s, %s)",
                (second_id, self.campaign_id, "Second event", "Economy", "The toll office closed."),
            )
        second_result = self.proposals.review(second_id, action="approve", edited_summary=None, reason=None)

        canon_ids = [item["id"] for item in self.proposals.list_canon(self.campaign_id)]
        self.assertLess(
            canon_ids.index(first_result["createdCanonId"]),
            canon_ids.index(second_result["createdCanonId"]),
            "expected the earlier-approved canon entry to come first (chronological, not newest-first)",
        )


if __name__ == "__main__":
    unittest.main()
