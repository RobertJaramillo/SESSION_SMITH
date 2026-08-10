"""Postgres-backed regression tests for the real worker pipeline behind the API.

Skipped unless DATABASE_URL is configured (see backend/db.py). These exercise the
actual HTTP routes end to end (submit_notes -> worker.extract_memory -> backend.store
-> Postgres, and submit_prep_job -> worker.generate_session_prep -> backend.store ->
Postgres) with the deterministic DemoProvider, so they catch wiring regressions a
unit test that mocks backend.store would miss.
"""

from __future__ import annotations

import asyncio
import unittest

from backend.db import connect, postgres_enabled
from backend.migrate import apply_migrations
from backend.repositories.campaigns import PostgresCampaignRepository
from backend.tests._asgi_client import request


@unittest.skipUnless(postgres_enabled(), "DATABASE_URL is not configured")
class WorkerPipelineIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        apply_migrations()
        self.campaigns = PostgresCampaignRepository()
        campaign = self.campaigns.create(name="Worker wiring test", description="")
        self.campaign_id = campaign["campaignId"]

    def tearDown(self) -> None:
        with connect(autocommit=True) as connection:
            connection.execute("DELETE FROM campaigns WHERE id = %s", (self.campaign_id,))

    def test_note_extraction_writes_a_demo_backed_proposal(self) -> None:
        async def scenario() -> None:
            _, submitted = await request(
                "POST",
                f"/v1/campaigns/{self.campaign_id}/notes",
                {
                    "content": "The Iron Court raised bridge tariffs. Oaths now require a blood price.",
                    "sessionNumber": "1",
                    "title": "Session one",
                },
            )
            job_id = submitted["data"]["jobId"]
            response_status, job = await request("GET", f"/v1/jobs/{job_id}")
            self.assertEqual(response_status, 200)
            self.assertEqual(job["data"]["status"], "succeeded")

        asyncio.run(scenario())

        with connect() as connection:
            row = connection.execute(
                "SELECT model_provider, prompt_version, proposed_summary FROM memory_proposals WHERE campaign_id = %s",
                (self.campaign_id,),
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["model_provider"], "demo")
        self.assertEqual(row["prompt_version"], "note_extraction.v1")
        self.assertIn("Iron Court", row["proposed_summary"])

    def test_world_builder_submission_gets_a_proposal_per_category_not_one_blob(self) -> None:
        """Regression test for the category-assignment bug: a multi-category
        World Builder submission used to collapse into one guessed category
        (or "General Overview") because category was derived after the fact
        from the whole proposal text. Each labeled entry should now land in
        its own category, taken directly from the entry's own label."""

        async def scenario() -> None:
            _, submitted = await request(
                "POST",
                f"/v1/campaigns/{self.campaign_id}/notes",
                {
                    "content": (
                        "[Economy] General economy\nThis world trades in souls, not money.\n\n"
                        "[Politics] Ruling powers\nTribes and races hold old grudges over territory."
                    ),
                    "sessionNumber": "0",
                    "title": "World Builder submission",
                },
            )
            job_id = submitted["data"]["jobId"]
            response_status, job = await request("GET", f"/v1/jobs/{job_id}")
            self.assertEqual(response_status, 200)
            self.assertEqual(job["data"]["status"], "succeeded")

        asyncio.run(scenario())

        with connect() as connection:
            rows = connection.execute(
                "SELECT category FROM memory_proposals WHERE campaign_id = %s ORDER BY category",
                (self.campaign_id,),
            ).fetchall()
        categories = {row["category"] for row in rows}
        self.assertEqual(categories, {"Economy", "Politics"})

    def test_job_history_lists_a_world_builder_submission_by_session_number(self) -> None:
        async def scenario() -> None:
            _, submitted = await request(
                "POST",
                f"/v1/campaigns/{self.campaign_id}/notes",
                {
                    "content": "[Economy] Coin shortage\nSilver is scarce after the mines flooded.",
                    "sessionNumber": "0",
                    "title": "World Builder submission",
                },
            )
            job_id = submitted["data"]["jobId"]
            await request("GET", f"/v1/jobs/{job_id}")  # let the background task settle before listing

            response_status, listed = await request("GET", f"/v1/campaigns/{self.campaign_id}/jobs")
            self.assertEqual(response_status, 200)
            job = next(item for item in listed["data"] if item["id"] == job_id)
            self.assertEqual(job["sessionNumber"], 0)
            self.assertEqual(job["type"], "extract_memory")
            self.assertEqual(job["status"], "succeeded")
            self.assertIsNone(job["error"])

        asyncio.run(scenario())

    def test_build_world_two_pass_generates_interlinked_canon_without_sealing(self) -> None:
        """build-world -> worker.build_world (bible Stage 1 -> expand Stage 2) ->
        store -> Postgres. Every proposal is world_expand.v1, references the shared
        bible anchor (interlinked), and the world is NOT sealed until the explicit
        seal-world action. Regenerate replaces the prior pending draft."""

        async def scenario() -> None:
            await request("POST", f"/v1/campaigns/{self.campaign_id}/entries", {
                "category": "politics", "title": "The Iron Court",
                "note": "The Iron Court taxes river crossings near Kestrel Vale.", "tags": [],
            })
            _, submitted = await request(
                "POST", f"/v1/campaigns/{self.campaign_id}/build-world",
                {"generateCategories": ["laws", "player_characters"]},
            )
            job_id = submitted["data"]["jobId"]
            response_status, job = await request("GET", f"/v1/jobs/{job_id}")
            self.assertEqual(response_status, 200)
            self.assertEqual(job["data"]["status"], "succeeded")

            # Not sealed by the build.
            _, campaign = await request("GET", f"/v1/campaigns/{self.campaign_id}")
            self.assertEqual(campaign["data"]["worldStatus"], "draft")

            # Regenerate replaces the prior pending draft (superseded -> rejected).
            _, regen = await request(
                "POST", f"/v1/campaigns/{self.campaign_id}/build-world",
                {"generateCategories": ["laws", "player_characters"]},
            )
            await request("GET", f"/v1/jobs/{regen['data']['jobId']}")

            # Explicit seal, then read-only.
            seal_status, _ = await request("POST", f"/v1/campaigns/{self.campaign_id}/seal-world", {})
            self.assertEqual(seal_status, 200)
            rebuild_status, _ = await request(
                "POST", f"/v1/campaigns/{self.campaign_id}/build-world", {"generateCategories": []},
            )
            self.assertEqual(rebuild_status, 409)

        asyncio.run(scenario())

        with connect() as connection:
            rows = connection.execute(
                "SELECT category, status, model_provider, prompt_version, proposed_summary FROM memory_proposals WHERE campaign_id = %s AND status = 'pending' ORDER BY category",
                (self.campaign_id,),
            ).fetchall()
        categories = {row["category"] for row in rows}
        self.assertTrue({"General Overview", "Politics", "Laws", "Player Characters"} <= categories)
        self.assertTrue(all(row["prompt_version"] == "world_expand.v1" for row in rows))
        self.assertTrue(all(row["model_provider"] == "demo" for row in rows))
        # Interlinked: every expanded proposal references the shared bible anchor.
        self.assertTrue(all("Iron Court" in row["proposed_summary"] for row in rows))

    def test_prep_job_writes_a_demo_backed_session_prep(self) -> None:
        async def scenario() -> None:
            _, submitted = await request(
                "POST",
                f"/v1/campaigns/{self.campaign_id}/prep-jobs",
                {"goal": "Confront the Iron Court about the new tariffs", "tone": "tense", "memories": ""},
            )
            job_id = submitted["data"]["jobId"]
            response_status, job = await request("GET", f"/v1/jobs/{job_id}")
            self.assertEqual(response_status, 200)
            self.assertEqual(job["data"]["status"], "succeeded")
            self.assertTrue(job["data"]["result"]["outline"])
            self.assertTrue(job["data"]["result"]["prepId"])

        asyncio.run(scenario())

        with connect() as connection:
            row = connection.execute(
                "SELECT model_provider, prompt_version, sections FROM session_preps WHERE campaign_id = %s",
                (self.campaign_id,),
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["model_provider"], "demo")
        self.assertEqual(row["prompt_version"], "session_prep.v1")
        self.assertTrue(row["sections"]["main_beats"])

    def test_prep_job_incorporates_the_gms_manually_selected_memories(self) -> None:
        """The 'Use memories' field used to be accepted by the API and silently
        discarded. Confirms it now actually reaches the generated prep."""

        async def scenario() -> None:
            _, submitted = await request(
                "POST",
                f"/v1/campaigns/{self.campaign_id}/prep-jobs",
                {"goal": "Confront the Iron Court", "tone": "tense", "memories": "Mira the smuggler betrayed the party in session 4."},
            )
            job_id = submitted["data"]["jobId"]
            response_status, job = await request("GET", f"/v1/jobs/{job_id}")
            self.assertEqual(response_status, 200)
            self.assertEqual(job["data"]["status"], "succeeded")
            outline_text = " ".join(job["data"]["result"]["outline"])
            self.assertIn("Mira the smuggler betrayed", outline_text)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
