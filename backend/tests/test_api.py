"""Contract smoke tests for the FastAPI development API.

They use the ASGI interface directly so they stay dependency-free (the project
does not need httpx merely to test its own API contract).
"""

from __future__ import annotations

import asyncio
import unittest

import backend.app as campaign_api
from backend.db import postgres_enabled
from backend.repositories.campaigns import InMemoryCampaignRepository
from backend.tests._asgi_client import request, request_raw


def _reportlab_available() -> bool:
    try:
        import reportlab  # noqa: F401
        return True
    except Exception:
        return False


@unittest.skipIf(
    postgres_enabled(),
    "In-memory contract test: endpoints branch on postgres_enabled(), so this only "
    "holds without DATABASE_URL. The Postgres path is covered by test_worker_pipeline "
    "and test_proposals_repository.",
)
class ApiContractTests(unittest.TestCase):
    def setUp(self) -> None:
        campaign_api.store = campaign_api.CampaignStore()
        campaign_api.campaigns = InMemoryCampaignRepository(campaign_api.store)

    def test_note_review_and_canon_lifecycle(self) -> None:
        async def scenario() -> None:
            response_status, entry = await request(
                "POST",
                "/v1/campaigns/campaign_glass_moon_exile/entries",
                {
                    "category": "economy",
                    "title": "Coin shortage",
                    "note": "Silver is scarce after the mines flooded.",
                    "tags": ["session_0", "scarcity"],
                },
            )
            self.assertEqual(response_status, 201)
            self.assertEqual(entry["data"]["note"], "Silver is scarce after the mines flooded.")
            self.assertEqual(entry["data"]["category"], "economy")

            response_status, submitted = await request(
                "POST",
                "/v1/campaigns/campaign_glass_moon_exile/notes",
                {"content": "The Iron Court raised bridge tariffs.", "sessionNumber": "1", "title": "First crossing"},
            )
            self.assertEqual(response_status, 202)

            job_id = submitted["data"]["jobId"]
            response_status, job = await request("GET", f"/v1/jobs/{job_id}")
            self.assertEqual(response_status, 200)
            self.assertEqual(job["data"]["status"], "succeeded")

            response_status, proposals = await request(
                "GET", "/v1/campaigns/campaign_glass_moon_exile/memory-proposals", query="status=pending"
            )
            self.assertEqual(response_status, 200)
            self.assertGreaterEqual(len(proposals["data"]), 1)

            proposal_id = proposals["data"][0]["id"]
            response_status, approved = await request("PATCH", f"/v1/memory-proposals/{proposal_id}", {"action": "approve"})
            self.assertEqual(response_status, 200)
            canon_id = approved["data"]["createdCanonId"]

            response_status, canon = await request("GET", "/v1/campaigns/campaign_glass_moon_exile/canon-events")
            self.assertEqual(response_status, 200)
            self.assertIn(canon_id, [item["id"] for item in canon["data"]])
            approved_canon = next(item for item in canon["data"] if item["id"] == canon_id)
            self.assertEqual(approved_canon["origin"], "session_notes")

            response_status, jobs = await request("GET", "/v1/campaigns/campaign_glass_moon_exile/jobs")
            self.assertEqual(response_status, 200)
            self.assertIn(job_id, [item["id"] for item in jobs["data"]])

        asyncio.run(scenario())

    def test_build_reviews_and_seals_via_explicit_action(self) -> None:
        async def scenario() -> None:
            cid = "campaign_glass_moon_exile"
            _, campaign = await request("GET", f"/v1/campaigns/{cid}")
            self.assertEqual(campaign["data"]["worldStatus"], "draft")

            # One entry (naming an anchor) + one checked empty category.
            await request("POST", f"/v1/campaigns/{cid}/entries", {
                "category": "politics", "title": "The Iron Court",
                "note": "The Iron Court taxes river crossings near Kestrel Vale.", "tags": [],
            })
            _, submitted = await request("POST", f"/v1/campaigns/{cid}/build-world", {"generateCategories": ["laws"]})
            job_id = submitted["data"]["jobId"]
            _, job = await request("GET", f"/v1/jobs/{job_id}")
            self.assertEqual(job["data"]["status"], "succeeded")

            # Build does NOT seal — the world stays draft for review.
            _, still_draft = await request("GET", f"/v1/campaigns/{cid}")
            self.assertEqual(still_draft["data"]["worldStatus"], "draft")

            # Two-pass output: an overview + the requested categories, all interlinked
            # (each summary references the shared anchor drawn from the entries).
            _, proposals = await request("GET", f"/v1/campaigns/{cid}/memory-proposals", query="status=pending")
            categories = {item["category"] for item in proposals["data"]}
            self.assertTrue({"General Overview", "Politics", "Laws"} <= categories)
            self.assertTrue(all("Iron Court" in item["summary"] for item in proposals["data"]))
            first_count = len(proposals["data"])

            # Regenerate replaces the pending draft (no pile-up).
            _, regen = await request("POST", f"/v1/campaigns/{cid}/build-world", {"generateCategories": ["laws"]})
            await request("GET", f"/v1/jobs/{regen['data']['jobId']}")
            _, proposals2 = await request("GET", f"/v1/campaigns/{cid}/memory-proposals", query="status=pending")
            self.assertEqual(len(proposals2["data"]), first_count)

            # Explicit seal locks the world; afterwards builds/entries are rejected.
            seal_status, _ = await request("POST", f"/v1/campaigns/{cid}/seal-world", {})
            self.assertEqual(seal_status, 200)
            _, sealed = await request("GET", f"/v1/campaigns/{cid}")
            self.assertEqual(sealed["data"]["worldStatus"], "sealed")
            rebuild_status, _ = await request("POST", f"/v1/campaigns/{cid}/build-world", {"generateCategories": []})
            self.assertEqual(rebuild_status, 409)
            entry_status, _ = await request("POST", f"/v1/campaigns/{cid}/entries", {"category": "npcs", "title": "x", "note": "y", "tags": []})
            self.assertEqual(entry_status, 409)

        asyncio.run(scenario())

    def test_world_export_scope_session_notes_excludes_world_builder_canon(self) -> None:
        async def scenario() -> None:
            cid = "campaign_glass_moon_exile"

            # Faithful path: a session note -> approved canon (origin: session_notes).
            await request("POST", f"/v1/campaigns/{cid}/notes", {"content": "The Iron Court raised bridge tariffs.", "sessionNumber": "1"})
            _, pending = await request("GET", f"/v1/campaigns/{cid}/memory-proposals", query="status=pending")
            note_proposal_id = pending["data"][0]["id"]
            _, note_approval = await request("PATCH", f"/v1/memory-proposals/{note_proposal_id}", {"action": "approve"})
            note_canon_id = note_approval["data"]["createdCanonId"]

            # Creative path: World Builder -> approved canon (origin: world_builder).
            _, build = await request("POST", f"/v1/campaigns/{cid}/build-world", {"generateCategories": ["races"]})
            await request("GET", f"/v1/jobs/{build['data']['jobId']}")
            _, world_pending = await request("GET", f"/v1/campaigns/{cid}/memory-proposals", query="status=pending")
            world_proposal_id = next(item["id"] for item in world_pending["data"] if item["category"] == "Races")
            _, world_approval = await request("PATCH", f"/v1/memory-proposals/{world_proposal_id}", {"action": "approve"})
            world_canon_id = world_approval["data"]["createdCanonId"]

            _, canon = await request("GET", f"/v1/campaigns/{cid}/canon-events")
            origins = {item["id"]: item["origin"] for item in canon["data"]}
            self.assertEqual(origins[note_canon_id], "session_notes")
            self.assertEqual(origins[world_canon_id], "world_builder")

            # Default scope (all) includes both; session_notes scope excludes the World-Builder entry.
            _, _, all_body = await request_raw("GET", f"/v1/campaigns/{cid}/world-export", query="format=md")
            all_text = all_body.decode()
            self.assertIn("Iron Court", all_text)
            self.assertIn("Races", all_text)

            _, _, scoped_body = await request_raw("GET", f"/v1/campaigns/{cid}/world-export", query="format=md&scope=session_notes")
            scoped_text = scoped_body.decode()
            self.assertIn("Iron Court", scoped_text)
            self.assertNotIn("**Category: Races**", scoped_text)

        asyncio.run(scenario())

    def test_world_export_markdown_has_sections_and_canon(self) -> None:
        async def scenario() -> None:
            cid = "campaign_ashes_of_kestrel_vale"  # seeded with canon in-memory
            status_code, headers, body = await request_raw("GET", f"/v1/campaigns/{cid}/world-export", query="format=md")
            self.assertEqual(status_code, 200)
            self.assertTrue(headers.get("content-type", "").startswith("text/markdown"))
            text = body.decode()
            self.assertIn("## World Overview", text)
            self.assertIn("## Canon by category", text)
            self.assertIn("**Category: Government Organizations**", text)
            self.assertIn("The Iron Court sets and enforces river-crossing tariffs.", text)

        asyncio.run(scenario())

    @unittest.skipUnless(_reportlab_available(), "reportlab not installed")
    def test_world_export_pdf_returns_pdf_bytes(self) -> None:
        async def scenario() -> None:
            cid = "campaign_ashes_of_kestrel_vale"
            status_code, headers, body = await request_raw("GET", f"/v1/campaigns/{cid}/world-export", query="format=pdf")
            self.assertEqual(status_code, 200)
            self.assertEqual(headers.get("content-type"), "application/pdf")
            self.assertTrue(body.startswith(b"%PDF-"))

        asyncio.run(scenario())
