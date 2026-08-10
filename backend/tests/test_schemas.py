"""Schema-robustness tests for the AI output contract.

A live LLM answers in json_object mode (not strict JSON-schema), so it drifts on
the small enums — most often putting a world-category slug like "magic_system"
into the proposal `type` field. One bad value must not fail the whole build; the
parser coerces unknown enums to safe defaults (the GM reviews every proposal).
"""

from __future__ import annotations

import unittest

from backend.schemas import ExtractionOutput, ProposalType, WorldCategoryLabel
from backend.tools.validation import validate_structured_output


class ProposalEnumCoercionTests(unittest.TestCase):
    def test_category_slug_in_type_is_coerced_not_rejected(self) -> None:
        # The exact shape that used to 500 a real-LLM build (see build-world).
        raw = (
            '{"proposals":['
            '{"type":"magic_system","category":"Magic Systems","proposed_summary":"Leyline oaths.","confidence":0.6},'
            '{"type":"political_structure","category":"Politics","proposed_summary":"Iron Court rules.","confidence":0.6}'
            ']}'
        )
        out = validate_structured_output(raw, ExtractionOutput)
        self.assertEqual([p.type for p in out.proposals], [ProposalType.canon_event, ProposalType.canon_event])
        # The real classification (category) is preserved, not lost.
        self.assertEqual([p.category for p in out.proposals], [WorldCategoryLabel.magic_systems, WorldCategoryLabel.politics])

    def test_unknown_category_falls_back_to_general_overview(self) -> None:
        raw = '{"proposals":[{"type":"canon_event","category":"NotACategory","proposed_summary":"x","confidence":0.5}]}'
        out = validate_structured_output(raw, ExtractionOutput)
        self.assertEqual(out.proposals[0].category, WorldCategoryLabel.general_overview)

    def test_missing_type_defaults_to_canon_event(self) -> None:
        raw = '{"proposals":[{"category":"Economy","proposed_summary":"x","confidence":0.5}]}'
        out = validate_structured_output(raw, ExtractionOutput)
        self.assertEqual(out.proposals[0].type, ProposalType.canon_event)

    def test_potential_conflicts_as_bare_string_is_wrapped_not_rejected(self) -> None:
        # Observed live (real OpenAI run, 2026-08-09): asked for "a short, specific
        # description", the model sometimes writes potential_conflicts as one string
        # instead of a single-item list, failing the whole extraction.
        raw = (
            '{"proposals":[{"category":"Economy","proposed_summary":"x","confidence":0.5,'
            '"potential_conflicts":"Not grounded in the source note."}]}'
        )
        out = validate_structured_output(raw, ExtractionOutput)
        self.assertEqual(out.proposals[0].potential_conflicts, ["Not grounded in the source note."])

    def test_potential_conflicts_as_empty_string_becomes_empty_list(self) -> None:
        raw = '{"proposals":[{"category":"Economy","proposed_summary":"x","confidence":0.5,"potential_conflicts":""}]}'
        out = validate_structured_output(raw, ExtractionOutput)
        self.assertEqual(out.proposals[0].potential_conflicts, [])


class TwoPassPromptRegistryTests(unittest.TestCase):
    def test_world_generation_prompt_versions_are_registered(self) -> None:
        from backend.schemas import WorldBible
        from backend.tools.prompting import _OUTPUT_SCHEMA_BY_VERSION, _SYSTEM_PROMPT_BY_VERSION

        self.assertIs(_OUTPUT_SCHEMA_BY_VERSION["world_bible.v1"], WorldBible)
        self.assertIs(_OUTPUT_SCHEMA_BY_VERSION["world_expand.v1"], ExtractionOutput)
        # Each has a dedicated system prompt (not the default extraction one).
        self.assertIn("world_bible.v1", _SYSTEM_PROMPT_BY_VERSION)
        self.assertIn("world_expand.v1", _SYSTEM_PROMPT_BY_VERSION)

    def test_world_bible_renders_a_prompt_block(self) -> None:
        from backend.schemas import WorldBible, WorldBibleEntity

        bible = WorldBible(premise="p", key_entities=[WorldBibleEntity(name="Iron Court", kind="faction")])
        block = bible.as_prompt_block()
        self.assertIn("PREMISE: p", block)
        self.assertIn("Iron Court", block)


class SessionPrepManualMemoriesTests(unittest.TestCase):
    """The GM's 'Use memories' input used to be accepted by the API and silently
    discarded — never reached the prompt. Locks the fix: present -> included and
    prioritized; blank -> the prompt is identical to before the field existed."""

    def test_manual_memories_are_rendered_as_their_own_labeled_block(self) -> None:
        from backend.schemas import ContextPackage, JobType
        from backend.tools.prompting import build_prompt

        ctx = ContextPackage(
            task=JobType.generate_session_prep, campaign_id="c1",
            gm_instructions="Confront the Iron Court",
            manual_memories="Mira the smuggler betrayed the party in session 4.",
        )
        req = build_prompt(ctx, "session_prep.v1")
        self.assertIn("GM_SELECTED_MEMORIES_START", req.user_prompt)
        self.assertIn("Mira the smuggler betrayed", req.user_prompt)
        self.assertIn("session-prep assistant", req.system_prompt)

    def test_blank_manual_memories_add_nothing_to_the_prompt(self) -> None:
        from backend.schemas import ContextPackage, JobType
        from backend.tools.prompting import build_prompt

        ctx = ContextPackage(
            task=JobType.generate_session_prep, campaign_id="c1",
            gm_instructions="Confront the Iron Court", manual_memories=None,
        )
        req = build_prompt(ctx, "session_prep.v1")
        self.assertNotIn("GM_SELECTED_MEMORIES", req.user_prompt)


class NoteExtractionGroundingDraftingRuleTests(unittest.TestCase):
    """Isolated precision fix: grounding was only ever a post-hoc check
    (_CONFLICT_GUIDANCE) -- this locks that it's now also a drafting rule.
    Deliberately does NOT touch extraction granularity/volume (see
    docs/KNOWN_LIMITATIONS.md's "tried and reverted" entry for why a bundled
    change including a granularity push was rolled back)."""

    def test_system_prompt_makes_grounding_a_drafting_rule(self) -> None:
        from backend.schemas import ContextPackage, JobType
        from backend.tools.prompting import build_prompt

        ctx = ContextPackage(task=JobType.extract_memory, campaign_id="c1", raw_note="x")
        req = build_prompt(ctx, "note_extraction.v1")
        self.assertIn("not just something to check", req.system_prompt)


if __name__ == "__main__":
    unittest.main()
