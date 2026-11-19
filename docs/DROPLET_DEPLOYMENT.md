# Droplet deployment

This runbook describes the current React/Vite, FastAPI, PostgreSQL and Caddy implementation. AI jobs run inside the API process. It does not assume the future Go services or separate worker described in SOFTWARE_ARCHITECTURE.md.

Run commands from the repository root on the Droplet. Substitute your production domain and server paths. This guide does not assert that the existing Droplet has already been configured this way.

## Prepare the deployment

Commit and push the intended changes, then check out the reviewed commit on the server. Preserve the existing Compose project name, database configuration and PostgreSQL volume; changing project names can create a different, empty volume. Never use `docker compose down -v` during an upgrade.

Before switching versions, pause application traffic/sign-ins and let active AI work finish. Jobs run in-process and are not handled by a separate durable queue worker. Record the current commit and retain a copy of the server configuration.

Back up the database while the database service is running. This command uses the database container's configured credentials rather than assuming the local defaults:

```bash
mkdir -p backups
chmod 700 backups
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "backups/pre-deploy-$(date +%Y%m%d-%H%M%S).sql"
```

Check that the dump completed successfully and keep a protected copy off the Droplet. Backups contain private campaign and account data. Restore tooling is in `scripts/restore-postgres.sh`; verify its database/user configuration before use.

## Server credentials and environment

Copy the Firebase Admin service-account JSON to a protected location outside the repository on the Droplet. Restrict its permissions, for example `chmod 600 /secure/server/path/firebase-admin.json`. The API container must be able to read it. A `/Users/...` path on a Mac does not exist on the server.

Set these values in the server's project-root `.env`; do not commit that file:

```dotenv
# Use local only during the existing-account migration below.
AUTH_PROVIDER=firebase
FIREBASE_PROJECT_ID=session-smith-515203
FIREBASE_WEB_API_KEY=<Firebase web API key>
FIREBASE_ADMIN_CREDENTIALS_PATH=/secure/server/path/firebase-admin.json

GOOGLE_CLIENT_ID=<Session Smith Google OAuth web client ID>
GOOGLE_CLIENT_SECRET=<matching OAuth client secret>
SESSION_SECRET=<stable random secret>
OAUTH_REDIRECT_URI=https://YOUR_DOMAIN/auth/google/callback
SESSION_COOKIE_SECURE=true
```

Generate SESSION_SECRET once, for example with `openssl rand -hex 32`, and retain it across restarts. It protects the OAuth handshake. Compose mounts the Admin JSON read-only at `/run/secrets/firebase-admin.json`; do not bake it into an image or expose it to the frontend.

Preserve the existing POSTGRES_DB, POSTGRES_USER and POSTGRES_PASSWORD. Changing POSTGRES_PASSWORD in `.env` does not rotate credentials in an initialized PostgreSQL volume. Never deploy the example database password to a new production database.

Keep the existing LLM_PROVIDER configuration appropriate to the deployment. OpenAI BYOK does not require a shared server OPENAI_API_KEY; it does require PostgreSQL and HTTPS. Gemini and hosted subscription billing are not implemented.

## HTTPS and network configuration

The checked-in `frontend/Caddyfile` listens on HTTP port 80 inside its container, published as port 8080. It does not provision production TLS as written.

Before allowing sign-ins, configure one of these deployment arrangements:

- Keep an existing HTTPS reverse proxy in front of the app, with the internal app port restricted to that proxy.
- Configure Caddy for the production hostname, publish ports 80/443, and persist its certificate data/configuration volumes.

In either arrangement, preserve routing for `/auth/*` and `/v1/*` to the API, SPA fallback for frontend routes, and the correct original HTTPS scheme/client address. Keep `SESSION_COOKIE_SECURE=true`. Narrow `FORWARDED_ALLOW_IPS` to trusted proxies; do not trust arbitrary internet clients. Keep one API worker until rate limiting is shared across processes.

Remove the database host-port publication if only containers need it, or bind it to loopback for administrative access. Port 5432 must not be public. The API host port is already bound to loopback. Restrict direct access to 8080 when an external proxy supplies HTTPS. Check both server and cloud firewalls against the chosen topology.

## Firebase and Google console configuration

Use the Session Smith project and its matching OAuth client, rather than the old Ad Integration Judge client.

- Register `https://YOUR_DOMAIN/auth/google/callback` as an authorized redirect URI on the Google OAuth web client, matching OAUTH_REDIRECT_URI exactly.
- Add the production hostname to Firebase Authentication's authorized domains.
- Enable Email/Password and Google providers. Require verified email for password access, configure the Firebase password policy for 12–256 characters, and enable email enumeration protection.
- Confirm consent branding/support contact, audience/test-user availability, and verification/reset email templates before launch.

For detailed identity migration and authentication behavior, see [Firebase authentication](FIREBASE_AUTH.md).

## Existing local accounts: one-time cutover

Use this section only if the database still uses local authentication. Keep public traffic paused throughout the cutover. Use `AUTH_PROVIDER=local` with the Firebase credentials configured, then build/start the updated services:

```bash
docker compose up -d --build api caddy
docker compose exec -T api python -m backend.migrate_firebase_users --dry-run
```

Resolve every reported identity collision before applying. Do not automatically merge accounts by matching email. After a successful dry run:

```bash
docker compose exec -T api python -m backend.migrate_firebase_users --apply
```

The migration preserves app IDs and campaign/friend relationships, imports password hashes and Google identities, and sends no emails. Unverified password users must verify their email when they next sign in. Existing local sessions stop working after activation.

Set `AUTH_PROVIDER=firebase`, then activate:

```bash
docker compose up -d --force-recreate api
```

If this deployment already uses the correct Firebase project, skip this import. In particular, do not rerun the local-user importer against accounts created natively through Firebase without assessing their existing identity mappings.

## Routine upgrades after Firebase activation

With the backup, reviewed commit, production configuration and traffic pause in place:

```bash
docker compose up -d --build api caddy
docker compose ps
```

API startup applies SQL migrations before serving. The current startup also runs the demo seeder; ownerless seed campaigns are hidden from normal accounts. Application data and permissions remain in PostgreSQL; Firebase supplies managed identity. Do not replace the production database with the local development database.

## Verify before reopening traffic

- Check `https://YOUR_DOMAIN/v1/healthz` and `/v1/readyz` return success.
- Sign in through Google; an already connected account should show Connected in Settings.
- Verify password registration/verification and reset email delivery using a controlled test account. Verify that new/reset passwords satisfy the configured policy.
- Check existing campaigns and friendships, private GM content restrictions, and player-only access with a separate account.
- Test campaign export and confirm logout removes access. Test a disposable ownership transfer only if appropriate; it immediately grants private GM access and demotes the previous owner.
- Confirm session cookies carry Secure and HttpOnly, and only intended public ports are reachable.

Do not include credentials, cookies, OAuth codes or reset links in screenshots or diagnostic output.

## Recovery boundary

Keep the previous commit and database backup available, but assess schema compatibility before rolling code back. A database restore discards writes made after the backup and does not undo changes in Firebase. After users change passwords in Firebase, switching AUTH_PROVIDER back to local can reactivate stale local password hashes; it is not a safe routine rollback. Keep traffic paused and resolve identity/configuration failures before reopening access.
