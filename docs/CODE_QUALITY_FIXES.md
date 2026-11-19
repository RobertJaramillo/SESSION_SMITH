# Code quality fixes — 19 November 2026

Changes are on the current ownership working tree and remain uncommitted.

## Functional fixes

- Recovery retains structured Firebase error codes. Unknown accounts still receive
  the enumeration-safe response; provider quota/configuration failures return a
  delivery-unavailable error rather than falsely claiming an email was sent.
- Logout is idempotent for expired/revoked sessions and remains CSRF protected.
  Firebase logout always invalidates the local cookie allowlist before attempting
  remote revocation. The frontend clears its account and AI credential even if
  the server cannot be reached.
- Campaign JSON export now reads durable campaign content through an owner-only
  API endpoint. PostgreSQL content is read in a repeatable-read transaction and
  includes raw notes, entries, canon, proposals, prep, entities and job records.
  Offline exports reflect actual offline state, clearly scoped to that mode.
- Session prep loads the saved outline when opening a campaign. Edited outlines
  can be saved and approved, and survive a remount/reload.
- Removed the nonfunctional archive action. Archiving is not represented as an
  available operation until a persistent implementation exists.
- Campaign listing filters membership in PostgreSQL and loads owner/player data
  in one query. Connections use a bounded psycopg pool with transaction rollback.
- Compose trusts forwarded addresses only from the local/Docker proxy boundary;
  direct host access to the API is restricted to loopback. The single API worker
  is explicit, so the in-process rate limiter has one counter per real client.
  Deployments using another proxy network must set FORWARDED_ALLOW_IPS narrowly.
  Multiple API replicas still require an ingress/shared limiter before scaling.
- Migration guards now run under pytest in the standard runner.
- Sealing a campaign preserves its model and visibility in the API response.
- Firebase initialization is synchronized. A stable OAuth SESSION_SECRET is
  required in managed mode; local configuration now has one without exposing it.
- OAuth authorization codes/state are redacted from Uvicorn access logging.

## Consolidation and cleanup

- Shared Dialog handles modal semantics, keyboard focus, Escape and focus return
  for sharing, account/settings updates, campaign creation and provider setup.
- Shared session-cookie helper keeps local and Firebase cookie flags consistent.
- JSON ASGI test requests now reuse the raw request transport.
- Production UI no longer reads hardcoded campaign workspace fixtures. Those
  fixtures and mock-generation helpers live under src/mocks.
- Deterministic backend fixtures live in demo_workflows.py. Selecting a live
  provider without PostgreSQL fails explicitly instead of silently returning
  demo output. Offline/demo and durable worker paths remain intentionally distinct.
- Removed PageId, navItems, CurrentUser, CategoryPill, _epoch, the uncalled polling
  stub, the unimplemented Anthropic adapter, and confirmed unused Python imports.
  Public domain contract models are retained; dynamic imports are not treated as
  unused exports.
- Untracked 5,115 installed dependency files plus the TypeScript build cache.
  Local node_modules remains installed; package-lock.json stays tracked.

## Validation

- Standard runner: 59 unittest tests (10 PostgreSQL-specific skips in offline
  mode), 12 pytest tests including migration guards, and 51 frontend tests.
- Separate disposable PostgreSQL database: all 20 account, sharing/ownership,
  export, pooling/rollback, worker and proposal tests passed with no skips.
- Frontend production build, ESLint and git whitespace checks pass.
- New regression coverage includes provider delivery errors, expired logout,
  proxy-aware client limits, private real exports, sealed response metadata,
  prep reload/save, modal focus containment and failed remote logout.
- Database tests ran in a temporary container database, which was removed after
  success. Existing campaign/user data was not used as a test fixture.
- No live AI calls or emails were sent by the test runs.

## Retained design boundaries

Local authentication is retained for offline development behind explicit provider
selection; Firebase remains the configured running provider. Removing local auth
entirely would eliminate offline development and requires a separate product
choice. Offline fixtures and SQL-backed workflows are now isolated and cannot
silently substitute for a selected live provider. Larger module splits can be
incremental rather than a rewrite of tested domain/worker contracts.
