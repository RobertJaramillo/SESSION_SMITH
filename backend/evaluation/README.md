# Evaluation Pipeline

Evaluates the **AI Campaign Orchestration** system by comparing the *world documents*
it produces against a **ChatGPT baseline**, using a blind, multi-evaluator,
fact-grounded methodology. This is the concrete implementation of the strategy
sketched in [AI_ARCHITECTURE.md §14](../../AI_ARCHITECTURE.md).

The design implements the methodology agreed in the project's evaluation thread,
including the reviewer's three refinements:

1. **Fact-grounded criteria** checked against the original session notes (not only
   subjective impressions).
2. **Blind evaluation** with **≥ 2 evaluators** and **inter-evaluator agreement**,
   plus a written **deep-dive discussion** wherever they disagree.
3. **Documented, reproducible generation** (model / prompt / settings) and
   **repeated runs**, because LLM output varies run-to-run.

---

## Quick start (offline, no API key)

```bash
cd backend && source .venv/bin/activate      # or your venv
python -m backend.evaluation.run_evaluation --runs 3
# -> writes backend/evaluation/out/report.html  (charts — open this in a browser)
#                                     report.md    (human-readable writeup)
#                                     report.json  (machine-readable, replayable)
```

`report.html` is a **self-contained dashboard** (inline SVG + CSS, no JS libraries,
no plotting dependency): KPI tiles, grouped-bar comparisons for the qualitative
rubric and the fact-grounded metrics, a per-criterion agreement chart, the
disagreement deep-dives, and a per-document table. It is light/dark aware with a
theme toggle, and uses a CVD-validated color palette (identity shown by legend +
direct labels, never color alone).

The offline run uses `DemoProvider` (see `fixtures.py`), a deterministic stand-in
that makes every stage return coherent, related output so you can see a full,
real-looking report with zero cost. Swap in a real provider for a real experiment.

---

## The methodology, step by step

```
session notes ──┬──► BASELINE generator (ChatGPT)  ─► world doc × N runs ─┐
                └──► OUR SYSTEM generator           ─► world doc × N runs ─┤
                                                                          ▼
   gold facts ◄── extract from the SAME notes                        BLIND all docs
   (ground truth)                                                         │
                                                                          ▼
                                        each of ≥2 EVALUATORS scores every blind doc
                                        • qualitative 1–5 rubric  (subjective)
                                        • fact-grounded metrics    (vs gold facts)
                                                                          │
                              ┌───────────────────────────────────────────┤
                              ▼                                           ▼
                     AGREEMENT (kappa,                          AGGREGATE per system
                     exact/adjacent) +                          (mean ± std over runs)
                     disagreement deep-dives                              │
                              └───────────────────────────────────────────┤
                                                                          ▼
                                                         ExperimentReport → report.md/json
```

1. **Gold reference** — `fact_checks.extract_gold_facts` distills a fixed set of
   important facts and entity relationships from the raw notes. It is the yardstick
   for the fact-grounded criteria. *For a graded run, a human should verify it.*
2. **Generation** — `generators.py` produces `--runs` documents per system. Both
   consume the **same** notes; each document records a full `GeneratorConfig`.
3. **Blinding** — `blinding.py` strips system identity and assigns shuffled labels
   (`DOC_A`, `DOC_B`, …). Judges only ever see the blind id and the text.
4. **Judging** — `judge.py` runs each evaluator over each blind document,
   producing both the qualitative 1–5 scores (with justifications) and the
   fact-grounded metrics (via `fact_checks.score_facts_against_document`).
5. **Agreement** — `agreement.py` computes quadratic-weighted Cohen's κ plus
   exact/within-1 agreement per criterion, and writes a discussion for every
   (document, criterion) whose scores spread by ≥ the threshold.
6. **Aggregation** — `aggregate.py` averages evaluators per document, then reports
   mean ± std per system across runs.
7. **Report** — `report.py` renders `report.md` (for humans) and `report.json`
   (machine-readable, replayable).

---

## Criteria

### Qualitative (1–5, judged; see `rubric.py`)
| Key | Meaning |
| --- | --- |
| `depth_completeness` | How thoroughly the world/material is covered. |
| `internal_consistency` | Does the document agree with itself? |
| `logical_coherence` | Do causes/consequences/structure hang together? |
| `faithfulness_to_notes` | Subjective faithfulness (companion to the fact counts). |

### Fact-grounded (measured against the notes; see `fact_checks.py`)
| Metric | Direction | Reviewer question it answers |
| --- | --- | --- |
| `preservation_rate` | ↑ better | How many important facts were preserved? |
| `creative_additions` | informational, not scored | How much creative material did the document add beyond the notes? (Not inherently bad — the World Builder is meant to add material; see `rubric.FACT_METRIC_HIGHER_IS_BETTER`.) |
| `contradictions` | ↓ better | How many factual contradictions occurred? |
| `relationship_accuracy` | ↑ better | How accurately were relationships maintained? |

---

## Running a *real* experiment

1. Set `OPENAI_API_KEY` in your environment or the repository's `.env` file. The
   evaluator reuses the main app's `OpenAIProvider` adapter.
2. Run with `--provider openai`. By default, generation uses `gpt-4o-mini` and
   the judges use `gpt-4o` plus `gpt-4o-mini`; override them with
   `--generation-model` and repeated `--judge-model` flags. Use distinct judge
   models where possible so the agreement number is more meaningful.
3. Document the exact models/settings — they are captured automatically in each
   `GeneratorConfig` and printed in the report's §1.
4. Use enough runs (`--runs 5+`) to characterize run-to-run variance.
5. **Human-in-the-loop:** review the auto-extracted gold facts before trusting the
   fact-grounded numbers, and spot-check the flagged disagreements in report §3.1.

## Evaluating exported Markdown or PDF documents

The pipeline can evaluate pre-generated world documents instead of generating new
ones. It accepts the platform's `.md` export and text-based `.pdf` export. The
original session-note JSON is still required because it remains the independent
source used to construct the gold facts.

**Export with `?scope=session_notes`, not the default `?scope=all`.** The
platform's `world-export` endpoint merges canon from two workflows with opposite
goals: `extract_memory()` (faithful to session notes) and the World Builder's
`build_world()` (deliberately creative — see `docs/AI_ARCHITECTURE.md` §6, "take
confident creative license"). The gold facts here are extracted purely from
session notes, so scoring the unscoped (`?scope=all`) export against them means
World-Builder-invented lore gets counted as a faithfulness failure it was never
attempting to avoid — this produced a misleadingly bad "our system" result in an
earlier run (see `out-openai-ledger-road-v7/report.md`). Always fetch
`GET /v1/campaigns/{id}/world-export?scope=session_notes&format=pdf` (or `.md`)
for the `--system-document` file when the goal is faithfulness-to-notes scoring.

```bash
python -m backend.evaluation.run_evaluation \
  --dataset synthetic-data/ashes_kestrel_10_session_data_set.json \
  --baseline-document /path/to/chatgpt-world.md \
  --system-document /path/to/campaign-world-scope-session_notes.pdf \
  --out backend/evaluation/out-file-comparison
```

Repeat either document flag to score multiple runs. Each file is recorded with its
path and format in the final report. Scanned or image-only PDFs are rejected rather
than being treated as empty text; OCR them before submitting them to the pipeline.

---

## Files

| File | Responsibility |
| --- | --- |
| `schemas.py` | Pydantic data contracts for every eval artifact. |
| `rubric.py` | Qualitative rubric + fact-grounded criteria definitions. |
| `generators.py` | Baseline (ChatGPT) and our-system document producers. |
| `blinding.py` | Blind/shuffle documents; hold the private un-blinding key. |
| `fact_checks.py` | Gold-fact extraction + scoring a doc against the notes. |
| `judge.py` | Blind LLM-as-judge (qualitative + fact-grounded per evaluator). |
| `agreement.py` | Inter-evaluator agreement stats + disagreement discussions. |
| `aggregate.py` | Per-document and per-system aggregation. |
| `report.py` | Render `report.md` + `report.json`; deterministic conclusion. |
| `charts.py` | Render the self-contained `report.html` dashboard (SVG charts). |
| `pipeline.py` | Orchestrator: `run_experiment(ExperimentConfig)`. |
| `dataset.py` | Load session notes from the sample dataset JSON. |
| `llm_json.py` | One validated-JSON-from-a-model helper (via the provider seam). |
| `fixtures.py` | `DemoProvider` for offline, deterministic demo runs. |
| `run_evaluation.py` | CLI entrypoint. |

---

## Limitations 

- **LLM-as-judge is imperfect.** Using ≥2 evaluators + agreement + human spot-checks
  mitigates but does not eliminate judge bias. Ideally include at least one human
  evaluator alongside the model judges.
- **The gold set is only as good as its verification.** Auto-extraction is a
  starting point; a human should confirm it for any graded result.
- **Small samples.** `--runs` is small by default; report variance, don't
  over-claim on a handful of generations.
- **The baseline is one config of one model.** Document it precisely and, if
  feasible, try more than one baseline setting.
- **World-Builder canon is out of scope for faithfulness scoring, by design.**
  `build_world()`'s prompts explicitly instruct creative invention (see
  `docs/AI_ARCHITECTURE.md` §6), so its output should never be scored against
  session-note gold facts. Score real product exports with `?scope=session_notes`
  (see "Evaluating exported Markdown or PDF documents" above). World-Builder
  output quality is currently not evaluated by this pipeline at all — a
  worthwhile future addition, not something this pipeline claims to cover today.
- **The default (no `--system-document`) "our system" generator is a standalone
  stand-in, not the real product.** `generators.py::generate_system_document`
  runs its own hand-written prompt, not `worker.extract_memory`/`build_world` —
  `run_evaluation.py` prints a warning when it's used. Always pass
  `--system-document` (see above) to evaluate the actual product.
