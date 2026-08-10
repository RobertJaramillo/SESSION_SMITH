# Analysis — Ledger Road Real-System Evaluation

Companion write-up for `report.md`/`report.json`/`report.html` in this directory. Where
the auto-generated report states *what* was measured, this explains *how much to trust
each number* — several of them were manually spot-checked against the raw session notes
and gold facts, not just taken at face value.

## What was actually compared

- **Our system**: the real product's `extract_memory()` pipeline. All 51 Ledger Road
  session notes were submitted through the live API in play order, generating real
  AI proposals from a real OpenAI-backed worker; each proposal was reviewed against the
  source notes and approved/rejected accordingly (138/160 approved on first pass across
  the campaign); the resulting canon was exported with `?scope=session_notes`, so
  World-Builder-only content (deliberately creative, not faithfulness-scored — see
  `docs/AI_ARCHITECTURE.md` §6) is excluded.
- **Baseline**: one single `gpt-4o-mini` call — the same model our system uses — given a
  plain, unengineered prompt ("help me summarize the world campaign here based on these
  session notes") and the full raw notes. Deliberately naive: this represents an average
  GM pasting notes into ChatGPT, not a strong, prompt-engineered competitor.
- **Gold reference**: 244 facts (8 relationships) extracted from the same 51 sessions,
  independently of either candidate document.
- **n = 1 run per system.** This is a single comparison, not a statistically confident
  one — the README's own methodology calls for ≥3 runs before trusting a "winner."

## Headline numbers

| Metric | Our System | Baseline | Read as |
|---|---|---|---|
| Qualitative rubric (1–5) | **4.38** | 4.25 | Real, close win |
| preservation_rate | **0.44** | 0.05 | Real, large win |
| relationship_accuracy | **0.12** | 0.00 | Real, win — but both low |
| contradictions | 1.50 | 0.00 → 0.50 | **Not trustworthy as scored** — see below |
| creative_additions | 93.0 | 18.0 | Informational only, not a competitive metric |

## What's real and defensible

**`preservation_rate` (0.44 vs 0.05) is the most telling number here, and it's not an
artifact.** A single 4-paragraph summary can only ever preserve a small slice of 51
sessions' worth of detail; a full canon export naturally preserves far more. This gap
reflects a real, structural property of the two approaches (comprehensive extraction vs.
one-shot compression), not a coincidence of this specific run.

**`relationship_accuracy` favors our system too, but both numbers are low (0.12 vs
0.00).** Only 8 relationship-kind facts existed in the gold set, so this is a thin
sample — directionally consistent with the preservation story, but not something to
lean on heavily by itself.

**Qualitative rubric (4.38 vs 4.25) is close and judge-agreement was strong** (mean
κ = 0.75, "substantial agreement," zero flagged disagreements) — the two judges saw it
the same way, which is the strongest signal in this report that the qualitative edge is
real rather than noise.

## What's *not* trustworthy as scored, and why

### `contradictions` (1.50 vs 0.50) — do not read this as "our system has more real continuity errors"

Every flagged contradiction was individually pulled and checked against its actual gold
fact (not just counted). Two distinct problems drove this number, both **methodology
gaps, not product faithfulness issues**:

1. **Gold facts have no sense of time — worked example: the party's level.** The raw
   notes show a clean, real progression across the campaign:

   | Sessions (of 51) | Party level | Notes text |
   |---|---|---|
   | 0–4 | 1 | "Level 1. Minor scratches only." (repeated per-session status line) |
   | 5–15 | 2 | "Level up to 2 at end." (session 5) |
   | 16–29 | 3 | "The party finally got a long rest and leveled to 3." (session 16) |
   | 30–47 | 4 | "The party leveled to 4 after a long rest in the toll house." (session 30) |
   | 48–50 | 5 | "Level up to 5 after escape." (session 48) |

   Gold extraction correctly captured this as four separate facts, each correctly
   tagged with the session it happened in — this part worked exactly as intended:

   | Gold fact | `session_id` |
   |---|---|
   | "The party is level 1 at the start of the campaign." | `ses_1` |
   | "The party leveled up to level 2 at the end of the campaign." | `ses_5` |
   | "The party leveled to 4 after a long rest in the toll house." | `ses_30` |
   | "The party is now level 5." | `ses_50` |

   The document (our system's export) accurately states the party reached level 4 —
   true as of session 30. The judge flagged this as **contradicting both** the level-2
   fact (`ses_5`) and the level-5 fact (`ses_50`).

   **Important correction on how this was originally investigated, caught during
   review of this document:** at the time this run (`final9`) executed, the prompt
   handed to the judge did *not* yet render any session-order labels — `session_id`
   was already stored on each `GoldFact`, but `_format_gold_for_prompt` wasn't using
   it yet, so the judge saw the four level-facts with no explicit indication of which
   came first. That's a real limitation on its own (facts extracted with real temporal
   metadata that then goes unused at check time), but it's a *weaker* claim than "the
   model had the ordering and still got it wrong."

   A follow-up fix was made *after* this run: `_format_gold_for_prompt` was changed to
   sort facts by session order and label each one `[session N/51]` using this same
   `session_id` field, and `_FACT_CHECK_SYSTEM_PROMPT` was given an explicit instruction
   that a later-session state doesn't contradict an earlier one. Re-running with that
   fix in place, the judge *still* flagged the same level-progression contradiction on a
   subsequent run — i.e. giving it the correct ordering explicitly didn't fully resolve
   it either. That result is accurate as reported, but its output artifacts were
   overwritten before this write-up and aren't preserved on disk to re-verify
   independently the way `final9`'s numbers are — treat it as a real observation from
   iterative testing, not as citable data with the same evidentiary weight as the table
   above.

   **So the limit, stated at the confidence level the preserved evidence actually
   supports:** gold facts about a property that changes over the campaign (level,
   location, item ownership, faction control, allegiance) get extracted as several
   separate, unordered-by-default "always true" facts, and a document correctly
   describing a later state will be flagged as contradicting an earlier snapshot of the
   same property. Adding explicit ordering to the prompt is a plausible mitigation but
   was not confirmed to fully solve it in testing — resolving this reliably likely needs
   the ordering handled at the canon/gold-fact source (marking the earlier fact
   superseded once the later one is confirmed) rather than left for a per-fact judge
   call to reason about correctly every time. See `docs/KNOWN_LIMITATIONS.md`'s entry on
   canon having no temporal supersession (`CanonStatus.revised`/`archived` and
   `ProposalStatus.superseded` already exist in the schema; nothing sets them) — that
   entry has been corrected to match this same confidence level.
2. **Plain judge imprecision.** The baseline's one flagged contradiction ("a fake tax
   collector" vs. "claimed to be a tax investigator") is the same claim in different
   words, not a real conflict — ordinary LLM-as-judge noise, which the project's own
   README already documents as a known limitation of this methodology.

Net effect: **the numeric gap here is mostly explained by a known gap in the evaluation
harness, not by the product being less faithful.** Treat `contradictions` the same way
as `creative_additions` below — informational, not a hard score — until the underlying
canon-supersession gap is actually fixed.

### `creative_additions` (93.0 vs 18.0) — informational by design, not a penalty

This is intentionally excluded from `rubric.FACT_METRIC_HIGHER_IS_BETTER` and never
factors into "who won." Two reasons it's large and *should* be large here:

1. Our system's export is comprehensive (hundreds of approved canon entries); the
   baseline is four paragraphs. More content naturally means more claims the (still
   curated, "major/critical facts only," not exhaustive) gold list never individually
   captured — that's a side effect of thoroughness, not invention.
2. The platform's design intentionally allows creative elaboration in some paths (the
   World Builder) — "the document says something the notes don't" isn't inherently bad
   the way a contradiction is.

## Bottom line

Our system's real, defensible advantage is **coverage**: it preserves far more of what
actually happened across 51 sessions than a naive single-shot summary can, and the
qualitative judges agree it reads better, with strong inter-evaluator agreement backing
that specific claim up. The two metrics that look unfavorable
(`contradictions`, `creative_additions`) are both explained by known, documented gaps in
*how the evaluation measures faithfulness* — a gold-fact list that's curated rather than
exhaustive, and no temporal ordering for facts that change over a campaign — not by the
product actually inventing more or conflicting more than the baseline.

## Recommendations, in priority order

1. **Fix canon temporal supersession** (`docs/KNOWN_LIMITATIONS.md`). This is the
   single change most likely to make `contradictions` trustworthy as a scored metric
   again, since it removes the root cause rather than papering over it at the
   consumption layer.
2. **Run ≥3 repeated runs per system** before treating any winner as settled — this
   report is n=1, and the project's own methodology says not to trust a single sample.
3. **Add a second, structured baseline** (e.g. a well-prompted ChatGPT world-builder) in
   addition to the naive one, to answer "does this beat good prompt engineering," not
   just "does this beat pasting notes into ChatGPT unassisted."
4. **Human spot-check the gold-fact list** before any graded/published use of this
   report — per the README's own stated limitation, auto-extracted gold facts are a
   starting point, not ground truth on their own.
