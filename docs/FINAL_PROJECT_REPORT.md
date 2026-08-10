# Generative AI Final Project Report

## Session Smith: AI Campaign Orchestration Platform

**Team members:** Robert Jaramillo, Jayaditya Peddisetti, Phuong-An Bui  
**Codebase:** https://github.com/RobertJaramillo/CAMPAGIN_ORCHESTRATOR

## 1. Problem Definition and Generative-AI Fit

### 1.1 Problem definition

Session Smith is an AI-assisted campaign-management platform for tabletop role-playing game (TTRPG) game masters (GMs). Its purpose is to preserve a coherent, persistent campaign world across campaigns that may run for three to five years. In that time, a campaign accumulates characters, factions, locations, unresolved hooks, player decisions, world events, and consequences across dozens or hundreds of sessions. Those details are usually fragmented across session notes, documents, chat logs, notebooks, and the GM's memory.

The core problem is continuity rather than creative writing. Players make unexpected decisions, new NPCs become important, and early details can gain new meaning many months later. A GM must reconcile this information while preparing each next session. Missing a fact can create a continuity error or weaken the long-term payoffs that make a campaign world compelling.

### 1.2 Why generative AI fits the problem

Generative AI can organize, retrieve, and synthesize unstructured campaign material, draft session preparation, and identify candidate updates in raw notes. But a general-purpose chat assistant does not maintain a durable, reviewable record of truth. It can introduce unsupported details, contradict established events, or reintroduce material that a GM has rejected. If an unreviewed output becomes later context, that error can be amplified.

Session Smith separates generation from authority. The language model generates drafts and candidate changes, but the GM reviews, edits, approves, rejects, or regenerates them. Only GM-approved information becomes campaign canon and can influence later retrieval. This makes GenAI a good fit: it reduces organizational work without assigning the model authority over the campaign.

The system supports three primary workflows:

1. **World building:** generate an initial, connected world bible from GM-provided setting and tone.
2. **Session preparation:** retrieve approved context and create an editable preparation draft.
3. **Session-note extraction:** turn raw notes into reviewable candidate memories and possible conflicts.

## 2. Baseline Comparison

The baseline represents a typical GM using a general chatbot without campaign-specific memory management. It receives the raw session notes and the simple prompt: *“Help me summarize the campaign world based on these session notes.”* The baseline has no controlled campaign memory, retrieval policy, structured output contract, validation layer, approval workflow, or provenance tracking.

Both systems use GPT-4o mini for generation. This is an important experimental control because it tests the value of Session Smith's orchestration rather than giving one side a stronger or more expensive model. The research question is: **Does an AI orchestration system help a GM manage campaign knowledge more reliably than a direct chatbot baseline using the same model?**

| Capability | Direct-chat baseline | Session Smith |
| --- | --- | --- |
| Context | Full raw notes in one prompt | Approved canon plus workflow-specific source material |
| Memory | No curated persistent memory | GM-approved canon is the only trusted retrieval source |
| Output | Free-form summary | Typed and schema-validated draft or proposal |
| Human control | Informal user judgment | Explicit approve, edit, reject, or regenerate actions |
| Future use | No controlled persistence | Only approved content can influence later generation |
| Provenance | Not managed | Model, prompt, tokens, cost estimate, and job metadata recorded |

## 3. Application and Technical Depth of GenAI Techniques

### 3.1 Retrieval-augmented generation and trust boundary

Session Smith is an applied GenAI system rather than a model-training project. Its technical contribution is the control layer around a foundation model: retrieval-augmented generation (RAG), structured prompts, schema validation, human review, and usage tracking.

RAG provides task-specific knowledge at inference time, but it also acts as a trust boundary. The retrieval layer loads approved campaign canon and relevant active entities, not every text item stored by the application. Raw notes are clearly labeled as material to analyze. Pending and rejected proposals are excluded from trusted retrieval, preventing an unreviewed model suggestion from reappearing as established fact.

### 3.2 Controlled generation pipeline

| Stage | System responsibility | Why it matters |
| --- | --- | --- |
| Request | The GM starts a world-build, session-prep, or note-extraction task. | Every AI action begins with user intent. |
| Retrieval | Worker loads approved canon and relevant context. | Grounds output in established campaign facts. |
| Prompt construction | Versioned instructions separate system rules, trusted context, raw notes, and output schema. | Improves consistency and reduces accidental instruction mixing. |
| Generation | Provider adapter sends the structured request to the model. | Keeps provider choice separate from workflows. |
| Validation | Response is parsed and validated with Pydantic schemas. | Prevents malformed or unexpected output from entering data. |
| Review | Drafts and proposed memories are shown to the GM. | Only human-approved facts become official canon. |

The World Builder is intentionally two-stage. It first produces a connected world bible with a premise, tensions, named entities, and open questions. It then expands requested categories using those shared details. This produces a more coherent world than independent category-by-category generation.

### 3.3 Application architecture and reliability controls

A React/Vite frontend provides the GM workspace. A FastAPI/Python backend owns API contracts, validation, repositories, and workflow entry points. PostgreSQL stores campaigns, raw notes, proposals, approved canon, jobs, and usage events. Generative-AI operations run through a job-oriented worker that performs retrieval, prompt construction, provider calls, validation, and persistence asynchronously.

The LLM provider is isolated behind an adapter that supports a deterministic demonstration provider and an OpenAI provider. This keeps model selection replaceable. The application also records model name, prompt version, input and output tokens, estimated cost, and job metadata. Bounded context, batching, and retries control cost and latency as campaign history grows.

## 4. Data, Knowledge Sources, and Dataset Quality

### 4.1 Knowledge sources and quality controls

| Knowledge source | Role | Trust status |
| --- | --- | --- |
| GM world-building inputs | Seed the initial setting and tone | User-authorized input |
| Raw session notes | Source material for memory extraction | Untrusted until reviewed |
| Pending proposals | AI-generated candidate facts and updates | Untrusted; excluded from retrieval |
| Approved campaign canon | Persistent entities, events, and relationships | Trusted; eligible for retrieval |
| Rejected proposals | Audit trail of declined content | Excluded from retrieval |

This separation prevents raw notes and AI guesses from becoming canon without approval. It also preserves provenance: the GM can distinguish an established fact from source material or an unapproved proposal.

### 4.2 Evaluation dataset

The evaluation uses the Ledger Road dataset: **51 campaign sessions** supplied to both systems as the same session-note source material. The pipeline produced a gold reference containing **244 important facts**, including **8 relationship facts**, extracted independently of either candidate output. This dataset is useful because it contains evolving characters, locations, ownership, factions, and campaign state across a long sequence rather than a short static prompt.

The dataset also has limits. Gold facts are initially auto-extracted and should receive human review before being treated as final ground truth. Some campaign properties change over time; a later approved fact may supersede an earlier state. Without explicit temporal supersession, correct historical states can appear contradictory. This limitation affects how contradiction metrics should be interpreted.

## 5. Evaluation Pipeline

The evaluation pipeline compares documents generated from the same source notes and uses controls intended to make results credible:

1. Extract important facts and entity relationships from the source notes to form the gold reference.
2. Generate or load a candidate document for the baseline and Session Smith.
3. Blind and relabel the documents so evaluators do not know their source.
4. Have two independent LLM judges score qualitative and fact-grounded criteria.
5. Compute inter-evaluator agreement and aggregate scores by system.
6. Produce HTML, Markdown, and JSON reports for inspection and reproducibility.

### 5.1 Evaluation metrics

| Metric | What it measures | Intended use |
| --- | --- | --- |
| Depth and completeness | Coverage of important campaign information | Higher is better |
| Internal consistency | Whether output contradicts itself | Higher is better |
| Logical coherence | Whether events and consequences are sensibly organized | Higher is better |
| Faithfulness to notes | Whether output reflects source notes | Higher is better |
| Preservation rate | Fraction of important gold facts retained | Higher is better |
| Relationship accuracy | Correctness of entity and event relationships | Higher is better |
| Creative additions | Claims beyond source notes | Informational only |
| Contradictions | Claims directly conflicting with source notes | Lower is better; interpret cautiously |
| Judge agreement | Consistency of evaluator scores | Higher is better |

Qualitative scores use a 1-5 rubric. Agreement is measured with quadratic-weighted kappa, exact agreement, and within-one-point agreement. The method is deliberately cautious: a model judge is imperfect and outputs can vary between runs. These findings are prototype evidence, not conclusive proof.

## 6. Experiments Performed and Results

### 6.1 Experimental setup

One blinded run was performed for each system. Both candidates were created from the same 51 Ledger Road sessions. The baseline was a single GPT-4o mini summary with the plain baseline prompt. The Session Smith candidate was created by submitting notes through the extraction workflow in play order, reviewing the resulting proposals, and exporting approved session-note-derived canon. Two independent LLM judges, GPT-4o and GPT-4o mini, scored the blinded documents.

The evaluation report records the candidate documents as external files because the evaluator consumed already-generated exports. The experiment log identifies the original baseline generation as GPT-4o mini. This distinction separates the generation experiment from the later document-evaluation step.

### 6.2 Results

| Metric | Session Smith | Baseline | Interpretation |
| --- | ---: | ---: | --- |
| Mean qualitative rubric score (1-5) | **4.38** | 4.25 | Small advantage for Session Smith |
| Preservation rate | **0.44** | 0.05 | Session Smith retained substantially more gold facts |
| Relationship accuracy | **0.12** | 0.00 | Session Smith preserved some relationships; both results are low |
| Contradictions | 1.50 | **0.50** | Diagnostic only because of temporal-state limitations |
| Creative additions | 93 | 18 | Informational; Session Smith exports a richer campaign record |
| Mean judge agreement (quadratic-weighted kappa) | **0.75** | - | Substantial agreement across qualitative criteria |

The clearest outcome is fact preservation. A one-shot summary retained 5% of curated gold facts, while Session Smith retained 44%. This supports the platform's central value proposition: a GM needs a durable record that carries information forward across many sessions, not only a short summary of recent events.

The qualitative edge is modest (4.38 versus 4.25), although the two judges showed substantial agreement. Relationship accuracy also favors Session Smith, but only eight relationship facts existed in the gold set, so that result is directional rather than decisive.

The contradiction count should not be read as evidence that Session Smith creates more real continuity errors. The current evaluator does not fully model facts that change over time. For example, a party can correctly progress from level 2 to level 4 to level 5, yet a document describing the level-4 state can be flagged against an earlier or later snapshot. This is a temporal-memory and evaluation limitation to address in future work.

### 6.3 Visualizations and tabular representations

Figures 1 and 2 visualize the qualitative and fact-grounded results. The results table above provides exact values and experiment context. The workflow diagram shows the controls used to create and evaluate the candidate documents.

**Figure 1.** *Qualitative evaluation scores. Session Smith has a small overall advantage, although the baseline scores higher on internal consistency in this one run.*

**Figure 2.** *Fact-grounded evaluation. Session Smith retains substantially more curated campaign facts than the one-shot baseline. Contradiction counts are diagnostic rather than conclusive because the evaluator does not yet fully handle time-varying campaign facts.*

## 7. Limitations and Future Work

| Limitation | Current impact | Future direction |
| --- | --- | --- |
| Lexical retrieval | Keyword matching can miss semantically related facts; more canon increases token cost. | Add embeddings, pgvector, and hybrid ranking. |
| Temporal canon state | Earlier facts are not consistently marked superseded by later state. | Add time-bounded records and revised or superseded states. |
| Conflict detection | Potential conflicts are generated by the model rather than independently verified. | Add deterministic checks and a second grounding pass. |
| Model instruction following | GPT-4o mini can omit requested categories. | Use batch-and-retry generation or task-appropriate models. |
| Fixed token budgets | One output limit is not ideal for every task. | Set task-specific limits and decompose larger tasks. |
| Typed entity updates | Some proposals do not yet update dedicated entity tables. | Implement type-specific storage and review logic. |
| Evaluation scale | One run per system and LLM-as-judge methods limit confidence. | Run at least three trials per system and add human evaluation. |

## 8. Conclusion

Session Smith demonstrates that the value of an AI campaign-management system is not merely generating more text. Its contribution is a controlled memory workflow: raw notes become reviewable proposals, GM-approved proposals become canon, and only canon supports future generation. This preserves GM authority while helping a long-running campaign remain coherent, searchable, and useful during preparation.

The prototype evidence supports this approach. On the Ledger Road evaluation, Session Smith retained far more curated facts than a naive one-shot GPT-4o mini summary and achieved a small qualitative advantage under blinded scoring. The results are not statistically conclusive, especially because the evaluation has one run per system and does not fully model evolving facts. The project establishes a practical base for future work in semantic retrieval, state-aware memory, conflict verification, and human evaluation.

## 9. Codebase and Supporting Materials

- **GitHub repository:** https://github.com/RobertJaramillo/CAMPAGIN_ORCHESTRATOR
- **AI architecture:** `docs/AI_ARCHITECTURE.md`
- **Software architecture:** `docs/SOFTWARE_ARCHITECTURE.md`
- **Evaluation report:** `backend/evaluation/out-real-ledger-road-final9/report.html`
- **Evaluation analysis:** `backend/evaluation/out-real-ledger-road-final9/ANALYSIS.md`
