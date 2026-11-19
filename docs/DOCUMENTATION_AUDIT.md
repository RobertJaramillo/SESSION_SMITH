# Documentation audit — 2026-11-19

Reviewed against the current working tree on `ownership`, including uncommitted changes. This describes repository implementation, not a verification of the deployed Droplet or live cloud configuration. Original guides have not been rewritten by this audit.

## Overall finding

The documentation remains useful, but there is no consistently maintained boundary between implemented behavior, development-only behavior, future design, and historical evidence. Authentication and sharing guides contain contradictory statements. The large architecture specifications describe substantially more infrastructure than exists.

Current implementation: React/Vite, Python FastAPI, PostgreSQL, and Caddy. AI jobs execute through FastAPI background tasks; there is no separate Go API or queue-worker service. Firebase mode supports managed email/password, verification, recovery, and Google identity. Application profiles, social relationships, permissions, and campaign data remain in SQL. Local authentication is a separate development mode. Campaign roles are Owner and Player.

## Document-by-document disposition

| Document | Status | Still applicable | Required correction / disposition |
| --- | --- | --- | --- |
| [Root README](../README.md) | Useful; targeted corrections required | Stack, basic run/test workflow, review-before-canon, SQL persistence | Remove Viewer; distinguish Firebase recovery from local auth limitations; explain OAuth state signing rather than claiming SESSION_SECRET signs all session cookies. Document all migrations through the migration runner. Clarify host versus Docker credential paths and OAuth callback ports. |
| [Frontend README](../frontend/README.md) | Substantially stale | React/Vite commands, workspace screens, real API default and opt-in mocks | Remove third dashboard group; replace claims that workspace/jobs remain in memory and a real worker is future work. Explain PostgreSQL versus no-database development modes. SQL records are authoritative; generated JSON documents are not the persistence model. |
| [Accounts and sharing](ACCOUNTS_AND_SHARING.md) | Contradictory; rewrite needed | Friendship consent, in-app invitations, seven-day expiry, owner/player restrictions, atomic ownership transfer | Opening credential-change claims describe local mode. “Ownership transfer is not exposed” contradicts the implemented section below. Email-verification/recovery absence is local-only. Firebase cookies differ from local opaque tokens. Campaign listing now uses SQL membership filtering. |
| [Firebase authentication](FIREBASE_AUTH.md) | Mostly current | Managed auth, migration, project ID, credential mount, verified-email gate, recovery, SQL identity mapping, production secure-cookie requirement | Label AUTH_PROVIDER=local as migration staging and firebase as final activation. Prefer the Session Smith project's OAuth client, rather than encouraging cross-project configuration. Compose already passes SESSION_COOKIE_SECURE; production must set it. Qualify account-wide logout revocation when the remote provider is unavailable. |
| [BYOK onboarding](BYOK_ONBOARDING.md) | Accurate key lifecycle; stale security premise | OpenAI support, tab-memory-only key, reload/sign-out clearing, HTTPS requirement, Gemini/hosted unavailable | Remove “UI-only beta gate” and prerequisites saying authentication/ownership still need implementation. Persistent encrypted keys and hosted quotas remain future work. Explain explicitly enabling a provider hard limit separately from spend alerts; avoid implying a precise guaranteed $5 ceiling. Google pricing/trial paragraphs are time-sensitive external claims and were not independently revalidated in this implementation audit. |
| [Known limitations](KNOWN_LIMITATIONS.md) | Mostly useful; prune stale items | Keyword retrieval, absent embedding implementation, normalized entity writers, retrieval preview, context limits, prompt-based conflict checks | Remove AnthropicProvider stub entry: the class was removed. Separate implemented account capabilities from development-mode limitations. Label model/evaluation observations as dated evidence rather than universal guarantees; replace fragile line-number references with symbols. |
| [Data model](DATA_MODEL.md) | Useful conceptual reference; stale schema coverage | Raw/proposed/approved separation, campaign domain, provenance, core campaign tables | Auth is no longer deferred. Add app_users, account_sessions, friendships, campaign_access, campaign_invitations, google_identities, firebase_identities. campaign_access determines per-user owner/player roles; campaigns.role is not that authority. Raw notes ARE sent as extraction input, although excluded from trusted retrieved canon. SQL snippets are explanatory, not authoritative bootstrap migrations. |
| [Software architecture](SOFTWARE_ARCHITECTURE.md) | Target design; unsuitable as current operations/API guide | Review gate, logical boundaries, PostgreSQL/Compose direction, future scaling ideas | Mark prominently as target/historical design. Go API/worker, durable queue claims, object-storage/backup services, broad entity CRUD, archive APIs, quotas and several route names do not describe the running implementation. Checked-in Caddy serves HTTP on 8080; domain HTTPS requires deployment configuration. Preserve useful future design rather than deleting it. |
| [AI architecture](AI_ARCHITECTURE.md) | Mixed current principles and roadmap | Structured generation, approved-memory retrieval, human review, provenance, creative world generation versus faithful note extraction | Add implemented/partial/planned labels. Current providers are demo/OpenAI; retrieval is Python keyword scoring. Embeddings, retrieval debug API, normalized entity application, persistent queue processing, and budget enforcement are not implemented. Go samples are illustrative. Raw task input and trusted memory need distinct wording. |
| [Evaluation README](../backend/evaluation/README.md) | Mostly applicable; setup defects | Offline deterministic pipeline, blind comparison, repeated runs, report outputs, explicit caveats about faithfulness and standalone generation | Fix architecture link to ../../docs/AI_ARCHITECTURE.md. Run backend/.venv/bin/python -m backend.evaluation.run_evaluation --runs 3 from repository root; current cd backend command breaks normal package resolution. Keep distinction between evaluation generator and actual product worker. |
| [Quality fixes](CODE_QUALITY_FIXES.md) | Dated implementation record | Remediation descriptions and recorded validation | Retain as a dated changelog. “Uncommitted” and exact test counts are snapshot facts, not permanent setup instructions. |

## Highest-priority corrections

1. **Authentication and recovery:** reconcile README, accounts, and BYOK guides around Firebase versus local development. The application is no longer a UI-only login prototype.
2. **Permissions:** eliminate Viewer and the claim that ownership transfer is unavailable. Preserve the warning that transfer grants private GM access and demotes the previous owner to Player.
3. **Deployment:** stop presenting Go services, durable queue recovery, automatic TLS, or server-independent credential paths as current behavior. The credential file must exist on the deployment host; a Mac path does not transfer to the Droplet.
4. **Trust boundary:** replace “raw notes NEVER fed to AI” with “raw notes are untrusted extraction input; approved canon is trusted retrieval context.” See backend/worker.py, backend/tools/prompting.py, and backend/rag.py.
5. **Reproducible setup:** fix the evaluation working directory/link and document environment overrides for host-run API versus Compose. Use backend/migrations and python -m backend.migrate as schema authority.

## External spending guidance

The BYOK recommendation is feasible but incomplete: OpenAI currently distinguishes spend alerts from explicitly enforced hard limits. Alerts do not stop requests. Hard-limit enforcement can lag and allow a small overshoot. The guide should name the enforcement setting and avoid promising an exact ceiling. Verified against [OpenAI spend limits documentation](https://developers.openai.com/api/docs/guides/spend-limits) on this audit date. Session Smith itself does not enforce monthly BYOK budgets.

## Historical material and sample inputs

These files should remain, with their purpose made clear. They are not current product or deployment instructions:

- `session-notes/session_00_initial_world_setup.md` through `session_10_the_bell_vault_opens.md`: eleven campaign narrative input files.
- `synthetic-data/dnd_campaign_session_notes_benchmark.md` and `dnd_campaign_world_b_session_notes_benchmark.md`: benchmark source material.
- Corresponding two files under `backend/evaluation/data/session_notes/`: evaluation inputs. Potential duplication is worth documenting, but changing/deleting copies requires checking experiment paths and reproducibility.
- `backend/evaluation/data/chatgpt/Ledger_Road_Naive_Summary.md`: baseline artifact.
- `backend/evaluation/out-real-ledger-road-final8/report.md`, `out-real-ledger-road-final9/report.md`, and `out-real-ledger-road-final9/ANALYSIS.md`: frozen experiment outputs/analysis. Their metrics concern their inputs and configurations, not guaranteed current product quality. Preserve historical results rather than silently updating them.

## Recommended documentation structure

Maintain a short current-system guide covering actual runtime, auth modes, permissions, jobs, storage, environment variables, and deployment boundaries. Root README should be its entry point. Keep Firebase, accounts, BYOK, and evaluation guides task-specific and link to this authority rather than repeating architecture facts. Label large specifications as target design and quality/evaluation records as historical snapshots. Move historical files only after updating links and experiment references.

## Review coverage and limits

Reviewed 30 project Markdown files: eleven guides, sixteen sample/baseline input files, and three historical evaluation outputs. Dependency/vendor documentation and generated test-cache documentation were excluded. A relative Markdown file-link scan found one broken target in the evaluation README; this does not validate section anchors or external URLs. Implementation evidence included Compose, API routes, authentication modules, migrations, repositories, retrieval/provider code, frontend flows, and the existing validation record. No application code, live Firebase settings, deployment, emails, or original guides were changed for this audit. No runtime tests were necessary for this report-only change.
