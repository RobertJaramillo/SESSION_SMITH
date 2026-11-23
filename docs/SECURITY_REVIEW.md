# Focused security review — 2026-11-19

Scope: current ownership working tree, authentication/session handling, campaign isolation, social/ownership flows, BYOK handling, deployment defaults, and dependency advisories. This was a quick code review and local test pass, not a penetration test or verification of the Droplet/Firebase console. No production data, real provider credentials, live AI requests or email deliveries were used. Application code was not changed by this review.

## Findings, in priority order

### S1 — High deployment risk: PostgreSQL published on all host interfaces

`compose.yaml:9` publishes `${POSTGRES_PORT:-5432}:5432`; the same file supplies a predictable fallback database password. The API and database share a Docker network, so public database exposure is unnecessary. Actual internet reachability depends on the Droplet's host/cloud firewalls; that was not tested. PostgreSQL still requires authentication, so this is not evidence of an unauthenticated data breach.

Fix: remove the host publication in production or bind it to `127.0.0.1`. Require an explicit strong production password, and verify host/cloud firewall rules. Changing an environment variable alone does not rotate an existing PostgreSQL user's password.

### S2 — Medium: raw provider errors persist into job history

`backend/app.py:438` and the corresponding prep/world-build handlers call `jobs.fail(job_id, str(error))`. `backend/repositories/jobs.py:94` persists this text, and job reads/campaign exports expose it to the campaign owner. Ownership transfer also grants the new owner access to these records.

Reproduction: constructed a synthetic OpenAI AuthenticationError containing a fake key, raised it from the extraction worker, and observed the fake key unchanged in the jobs.fail argument. No database or real provider was contacted. This proves arbitrary exception text can enter the persistence path; it does not establish that a live provider returns a complete key. Provider error bodies may include masked key fragments, request content or internal diagnostics. This also weakens the product's promise that BYOK credentials never enter job history.

Fix: map exceptions to bounded, safe public messages and stable error codes before persistence. Do not log raw exception bodies/headers as an alternative. Review existing failed-job records for sensitive material without printing it; sanitize historical records if needed. Test that synthetic key material never appears in stored errors, API responses or exports.

### S3 — Medium, potentially high with a shared server key: costly jobs have no admission limits

The rate limiter in `backend/access.py:36` covers registration, login, recovery and verification. Authenticated owners can repeatedly submit extraction/prep/world-building jobs (`backend/app.py:452`, `:526`, `:648`) without a per-user/per-campaign quota or an active-job limit. Open registration makes this a practical abuse boundary. Background jobs consume API-process/thread/database capacity; with a shared OPENAI_API_KEY they also consume the application's provider budget. BYOK reduces shared billing risk but does not prevent service exhaustion.

Fix: limit submission frequency and concurrent jobs by user/campaign, bound outstanding work globally, and impose server-funded budgets before offering a shared key. Enforce limits atomically in shared storage if more than one process can admit work. Add body-size limits at the ingress as well as model field limits.

### S4 — Medium maintenance finding: affected JavaScript dependency versions

`npm audit --omit=dev --json` reported six high-severity package entries, zero critical: nanoid, postcss, react-router, react-router-dom, source-map-js and vite. These are affected-package counts, not six independently demonstrated exploitable application flaws. react-router-dom inherits the router finding. Vite is currently classified as a production dependency even though the deployed frontend is static files served by Caddy.

Triage:

- React Router advisory GHSA-qwww-vcr4-c8h2 applies to unstable RSC APIs. This code uses client-side routing and no RSC APIs were found. Its maintainer advisory labels it moderate, despite the registry audit's high classification. Patch within the compatible 7.x line anyway (7.18.2 or newer patched release).
- Vite and source-map/PostCSS/nanoid findings primarily concern development/build paths in this deployment. Do not expose the development server publicly. Check each patched transitive version when updating the lockfile; avoid a blind forced major-version upgrade.
- The checked Vite advisory includes a fix in 8.1.6, while additional registry advisories may require a later release. Upgrade to a compatible release covering all returned advisories, then rerun audit, build and tests.

Sources: [React Router maintainer advisory](https://github.com/remix-run/react-router/security/advisories/GHSA-qwww-vcr4-c8h2), [Vite maintainer advisory](https://github.com/vitejs/vite/security/advisories/GHSA-rq7h-c2jc-7f22). Results are a dated snapshot; no dependency versions were changed during review.

## Additional hardening

- Production HTTPS is not configured by the checked-in Caddyfile. Compose defaults to local authentication and non-Secure cookies. The deployment runbook requires Firebase mode, HTTPS and SESSION_COOKIE_SECURE=true; introduce a production configuration that fails closed when these are missing.
- Caddy has no application-specific CSP or frame-embedding policy. Add a tested Content-Security-Policy, frame restriction, Referrer-Policy and nosniff; add HSTS at the actual HTTPS terminator after confirming TLS behavior. This is defense in depth, not evidence of a confirmed XSS issue.
- Python dependencies have broad ranges and no lockfile, so a future container build may resolve different packages. Pin/lock reviewed releases and scan the built container; the local environment audit cannot establish the exact container dependency set.
- Owner/member permission checks are generally enforced at request entry. Ownership transfer rechecks roles atomically, but other in-flight operations can overlap revocation/transfer. Consider transaction-level authorization for particularly sensitive writes if strict concurrent revocation is required.
- The authenticated friend-search endpoint deliberately reveals whether an email has an account and lacks its own request limit. Consider throttling enumeration and invitation spam as the beta audience expands.

## Checks that passed

- Focused backend suite: 24 tests ran successfully; one PostgreSQL-only test skipped. Covers account isolation, invitation consent/expiry, player restrictions, Google identity/linking, verification, cookie revocation and CSRF cases. These were offline/mock-provider checks, not fresh PostgreSQL integration tests.
- Campaign access is enforced server-side for campaign routes and indirect job/proposal IDs. Owner transfer rechecks the current owner and accepted friendship within a transaction.
- Firebase sessions verify signatures, project, expiration, revocation and verified email, with a SQL session allowlist. Cookies are HttpOnly/SameSite=Lax, with Secure controlled by HTTPS/production configuration.
- SQL queries inspected use bound values; dynamic column names are selected from fixed mappings. No unsafe React HTML insertion was found in the reviewed frontend.
- BYOK state is memory-only and sent through headers; the important exception is the error-persistence path above.
- A targeted scan of tracked and non-ignored working-tree files found no private-key blocks, service-account private keys or OpenAI-key-shaped strings. `.env` is ignored. This was not a full Git-history or all-provider secret scan.
- pip-audit inspected the installed local backend site-packages and reported no known vulnerabilities. The auditor was installed in an isolated /tmp environment; project dependencies were unchanged.

Review baseline: [OWASP authorization guidance](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) on server-side permission checks for every request.

## Release recommendation

Address S1 and S2 before public deployment; add S3 admission controls before exposing shared paid generation or opening registration broadly. Patch and re-audit affected dependencies, then verify the built container and production configuration. Live TLS/firewall checks, cloud provider configuration, recovery-email delivery and real Google sign-in remain deployment smoke tests. Passing the local checks is not a blanket security guarantee.
