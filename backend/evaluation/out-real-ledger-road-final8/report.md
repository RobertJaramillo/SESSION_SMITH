# Evaluation Report — campaign_ledger_road

- **Runs per system:** 1
- **Evaluators:** openai_judge_1_gpt-4o, openai_judge_2_gpt-4o-mini
- **Gold reference:** 259 facts (11 relationships) extracted from the session notes

> **Scope note:** the fact-grounded metrics below score faithfulness to session notes. The platform's World Builder (`build_world()`) is a deliberately creative co-author (see `docs/AI_ARCHITECTURE.md` §6) and its output is excluded from this comparison by design — score a `?scope=session_notes` world-export, not `?scope=all`, when the candidate is a real product export (see `backend/evaluation/README.md`).

## 1. Generation settings (reproducibility)

Both systems consumed the *same* session notes. Settings are recorded so the experiment can be reproduced despite run-to-run LLM variation.

### Baseline (ChatGPT)
- provider / model: `external_file` / `not_provided`
- prompt version: `external_document.v1`
- temperature: 0.0
- notes: Source file: /Users/phuonganbui/GenAI_Project/CAMPAGIN_ORCHESTRATOR/backend/evaluation/data/chatgpt/Ledger_Road_Naive_Summary.pdf (format: .pdf).

<details><summary>Prompt template</summary>

```text
External candidate document supplied for evaluation; no generation prompt is available.
```
</details>

### Our System
- provider / model: `external_file` / `not_provided`
- prompt version: `external_document.v1`
- temperature: 0.0
- notes: Source file: /Users/phuonganbui/GenAI_Project/CAMPAGIN_ORCHESTRATOR/backend/evaluation/data/session_smith/ledger_road_session_notes_scope.pdf (format: .pdf).

<details><summary>Prompt template</summary>

```text
External candidate document supplied for evaluation; no generation prompt is available.
```
</details>

## 2. System comparison (mean ± std across runs)

### Qualitative rubric (1–5, higher is better)

| Criterion | Our System | Baseline (ChatGPT) |
| --- | --- | --- |
| Depth & Completeness | 5.00 ± 0.00 (n=1) | 4.00 ± 0.00 (n=1) |
| Internal Consistency | 4.00 ± 0.00 (n=1) | 5.00 ± 0.00 (n=1) |
| Logical Coherence | 4.00 ± 0.00 (n=1) | 4.00 ± 0.00 (n=1) |
| Faithfulness to Source Notes | 4.50 ± 0.00 (n=1) | 4.00 ± 0.00 (n=1) |

### Fact-grounded metrics (checked against the notes)

- **preservation_rate** (↑ better): Fraction of important gold facts (from the notes) preserved in the document. Higher is better. Answers: 'How many important facts were preserved?'
- **creative_additions** (informational, not scored): Count of claims in the document not traceable to the notes — new material the document adds. Informational only, not scored: the platform's World Builder is meant to add creative material beyond the notes, so this isn't inherently bad on its own — outright contradictions (below) are the real signal of unfaithfulness. Answers: 'How much creative material did the document add beyond the notes?'
- **contradictions** (↓ better): Count of document claims that directly contradict the notes. Lower is better. Answers: 'How many factual contradictions occurred?'
- **relationship_accuracy** (↑ better): Fraction of character/location/faction/event relationships from the notes represented correctly. Higher is better. Answers: 'How accurately were relationships maintained?'

| Metric | Our System | Baseline (ChatGPT) |
| --- | --- | --- |
| preservation_rate | 0.40 ± 0.00 (n=1) | 0.06 ± 0.00 (n=1) |
| creative_additions | 226.00 ± 0.00 (n=1) | 15.50 ± 0.00 (n=1) |
| contradictions | 0.00 ± 0.00 (n=1) | 0.00 ± 0.00 (n=1) |
| relationship_accuracy | 0.36 ± 0.00 (n=1) | 0.00 ± 0.00 (n=1) |

## 3. Inter-evaluator agreement

Mean quadratic-weighted kappa across criteria = 0.75 (substantial agreement). 0 (document, criterion) case(s) exceeded the disagreement threshold and are discussed individually.

| Criterion | Quadratic-weighted κ | Exact agreement | Within-1 agreement |
| --- | --- | --- | --- |
| Depth & Completeness | 1.00 | 100% | 100% |
| Internal Consistency | 1.00 | 100% | 100% |
| Logical Coherence | 1.00 | 100% | 100% |
| Faithfulness to Source Notes | 0.00 | 50% | 100% |

### 3.1 Disagreements (deep dive)

_No (document, criterion) pair exceeded the disagreement threshold._

## 4. Per-document scores (blind)

Scores below are the mean across evaluators. `blind_id` is what the judges actually saw; the system column is revealed only after scoring.

| Blind ID | System | Run | Depth & Completeness | Internal Consistency | Logical Coherence | Faithfulness to Source Notes | preserved | creative additions | contradictions | rel.acc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DOC_A | Baseline (ChatGPT) | 0 | 4.0 | 5.0 | 4.0 | 4.0 | 0.06 | 15.5 | 0.0 | 0.00 |
| DOC_B | Our System | 0 | 5.0 | 4.0 | 4.0 | 4.5 | 0.40 | 226.0 | 0.0 | 0.36 |

## 5. Conclusion

Averaged over the qualitative rubric, our system scored 4.38 vs the baseline's 4.25 (1–5). Qualitative winner: **Our system**.
- preservation_rate: ours 0.40 vs baseline 0.06 → favors our system.
- relationship_accuracy: ours 0.36 vs baseline 0.00 → favors our system.
- contradictions: ours 0.00 vs baseline 0.00 → favors neither (tie).

These are automated results over a small sample; the numbers should be read together with the disagreement discussions in §3.1 and, ideally, a human spot-check of the flagged cases.
