"""Tests for the world-export Markdown builder (backend/exporting.py).

Offline and pure — locks the document structure the evaluation artifact depends
on: overview from General Overview, the two labeled sections, category ordering,
the `title: note` / canon-summary lines, and empty-category omission.
"""

from __future__ import annotations

import unittest

from backend.exporting import build_world_export_markdown


class WorldExportMarkdownTests(unittest.TestCase):
    def setUp(self) -> None:
        self.entries = [
            {"category": "general_overview", "title": "Tone", "note": "Dark political fantasy."},
            {"category": "economy", "title": "Coin shortage", "note": "Silver is scarce."},
            {"category": "politics", "title": "Rebels", "note": "River wards resist."},
        ]
        self.canon = [
            {"category": "Economy", "summary": "Food prices doubled after the ash storm."},
            {"category": "Government Organizations", "summary": "The Iron Court enforces river tariffs."},
            {"category": "General Overview", "summary": "The Flood of Bells reshaped the vale."},
        ]
        self.md = build_world_export_markdown("Ashes of Kestrel Vale", self.entries, self.canon)

    def test_has_the_three_sections_and_title(self) -> None:
        self.assertIn("# Ashes of Kestrel Vale — World Export", self.md)
        self.assertIn("## World Overview", self.md)
        self.assertIn("## Information provided when creating the world", self.md)
        self.assertIn("## Canon by category", self.md)

    def test_overview_pulls_general_overview_entry_and_canon(self) -> None:
        overview = self.md.split("## Information provided")[0]
        self.assertIn("- Tone: Dark political fantasy.", overview)
        self.assertIn("- The Flood of Bells reshaped the vale.", overview)

    def test_general_overview_is_not_duplicated_in_lower_sections(self) -> None:
        lower = self.md.split("## Information provided", 1)[1]
        self.assertNotIn("Category: General Overview", lower)

    def test_entries_and_canon_group_by_category_in_canonical_order(self) -> None:
        self.assertIn("**Category: Economy**\n- Coin shortage: Silver is scarce.", self.md)
        self.assertIn("**Category: Economy**\n- Food prices doubled after the ash storm.", self.md)
        # Economy precedes Politics in WORLD_CATEGORIES order.
        self.assertLess(self.md.index("Category: Economy"), self.md.index("Category: Politics"))

    def test_empty_world_states_the_placeholders(self) -> None:
        md = build_world_export_markdown("Empty World", [], [])
        self.assertIn("No overview provided.", md)
        self.assertIn("No world-build entries were recorded.", md)
        self.assertIn("No approved canon yet.", md)


class WorldExportOriginFilterTests(unittest.TestCase):
    """Locks the evaluation-scoping fix: `origin_filter` must exclude
    World-Builder-invented canon from a faithfulness-scoped export while
    leaving the default (unscoped) GM-facing export untouched."""

    def setUp(self) -> None:
        self.entries = [{"category": "general_overview", "title": "Tone", "note": "Dark fantasy."}]
        self.canon = [
            {"category": "Economy", "summary": "Grain tithes doubled this year.", "origin": "session_notes"},
            {"category": "Races", "summary": "The invented Sylvan Kin walk among the vale.", "origin": "world_builder"},
            {"category": "Politics", "summary": "Pre-provenance canon of unknown origin.", "origin": "unknown"},
        ]

    def test_default_scope_includes_every_origin(self) -> None:
        md = build_world_export_markdown("Ashes", self.entries, self.canon)
        self.assertIn("Grain tithes doubled this year.", md)
        self.assertIn("Sylvan Kin", md)
        self.assertIn("Pre-provenance canon of unknown origin.", md)

    def test_session_notes_scope_excludes_world_builder_and_unknown(self) -> None:
        md = build_world_export_markdown("Ashes", self.entries, self.canon, origin_filter="session_notes")
        self.assertIn("Grain tithes doubled this year.", md)
        self.assertNotIn("Sylvan Kin", md)
        self.assertNotIn("Pre-provenance canon of unknown origin.", md)


if __name__ == "__main__":
    unittest.main()
