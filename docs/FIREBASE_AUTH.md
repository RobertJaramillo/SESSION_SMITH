# Firebase Authentication

For server configuration, HTTPS, backups and rollout order, see the
[Droplet deployment runbook](DROPLET_DEPLOYMENT.md).

Firebase mode supports email/password, Google sign-in, verification emails and
password recovery. All identity tokens stay on the server. The browser receives
an HttpOnly, SameSite=Lax Firebase session cookie. The backend validates its
signature, project, expiry, revocation and disabled-user state on every request.
A local session allowlist also invalidates copied cookies immediately on logout,
including Firebase’s same-second revocation edge case.
Firebase password reset invalidates older sessions. Logout revokes all sessions
for the account, including other browsers. Campaign/friend authorization remains
in our database; provider identities map to existing account IDs.

## Configure the existing Google Cloud project

1. In https://console.firebase.google.com/ choose **Add project** and select the
   existing Google Cloud project `session-smith-515203`.
2. Open Authentication → Get started → Sign-in method. Enable Email/Password and
   Google. For Google, use the same Web OAuth client ID and secret as the app's
   current `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` (Google provider settings
   allow an external project client configuration). Keep the current Google
   callback registered: `http://localhost:8080/auth/google/callback`.
3. Add `localhost` to Authentication's authorized domains. Enable email
   enumeration protection. Set the password policy to **Require**, minimum **12**
   and maximum **256** characters. Leave forced upgrades on sign-in off so existing
   passwords continue working; creation and reset must meet the new policy.
4. Customize the verification and password-reset email templates. Firebase's
   hosted action pages handle the single-use links and password entry. Keep the
   hosted action handler URL; users return to our login page after completion.
5. In Project settings → General, obtain the Web API key. If needed register a
   Web app first. In Project settings → Service accounts, generate an Admin SDK
   JSON credential and store it outside the repository. Never put it in the
   frontend, commit it, paste it into chat or print its contents.

Add these to the project-root `.env`, preserving current values:

```dotenv
AUTH_PROVIDER=local
FIREBASE_PROJECT_ID=session-smith-515203
FIREBASE_WEB_API_KEY=your-web-api-key
FIREBASE_ADMIN_CREDENTIALS_PATH=/absolute/path/outside/repo/firebase-admin.json
# Keep existing GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET and SESSION_SECRET.
OAUTH_REDIRECT_URI=http://localhost:8080/auth/google/callback
```

Production needs HTTPS and `SESSION_COOKIE_SECURE=true`. The Compose deployment
must pass that setting through to the API. The Admin credential is mounted
read-only at `/run/secrets/firebase-admin.json`; it is not baked into the image.
For non-Docker development, set `GOOGLE_APPLICATION_CREDENTIALS` to its local path.

## Migrate existing users before switching

Take a database backup first. Pause account creation/sign-in during the cutover
so the user list cannot change between migration and activation. Start with
`AUTH_PROVIDER=local` and install/build the new backend:

```bash
docker compose up -d --build api caddy
docker compose exec api python -m backend.migrate_firebase_users --dry-run
docker compose exec api python -m backend.migrate_firebase_users --apply
```

The dry run validates Firebase email and UID collisions before importing. Apply
preserves local IDs, imports standard scrypt hashes with the original parameters,
and imports linked Google subject IDs. It writes `firebase_identities`; existing
campaigns, friends and invitations are untouched. It sends no emails. The command
can be rerun after a partial failure; it does not overwrite existing Firebase users.
Do not migrate to a Firebase project already used by another application.

Unverified password accounts remain unverified. Their next login requires email
verification; they can use **Resend verification email** with their existing
password or use **Forgot your password?**. Google accounts retain Google sign-in. Password users can also use Settings →
Connect Google account after a recent sign-in, selecting the same verified email.
New Firebase identities never gain access to an existing app account merely by
claiming the same email. Conflicting identities need an explicit administrator
migration rather than automatic linking.

After migration succeeds, change `.env` to `AUTH_PROVIDER=firebase` and run:

```bash
docker compose up -d --force-recreate api
```

Existing local sessions stop working. There is no fallback to local password or
Google sessions in Firebase mode. Missing configuration fails closed. Keep local
authentication for offline development only; reverting to it after Firebase users
have changed passwords would re-enable stale legacy password hashes.

## Smoke test

- New password signup sends verification email and grants no session yet.
- Unverified login is denied; resend verification works; verify then sign in.
- Forgot password gives the same response for existing and missing addresses.
- Reset via the Firebase email, then sign in with the new password. Old password
  and pre-reset browser sessions must fail.
- Continue with Google opens the existing OAuth flow and issues a Firebase session.
- Migrated accounts retain owned/shared campaigns and friendships.
- A second user cannot open someone else's private campaign or GM notes.
- Logout invalidates the cookie, including copies in another browser.

Display names can still be edited in the app. Email changes are currently disabled
in Firebase mode until a verified email-change flow is added. Password changes use
the managed reset email from Settings. Existing Google accounts can use recovery
to add a password when Firebase supports that account's configured provider policy.

Offline tests mock Firebase's boundary; they do not send emails or create users.
Live smoke tests require the project configuration above. References:
https://firebase.google.com/docs/auth/admin/manage-cookies
https://firebase.google.com/docs/reference/rest/auth
https://firebase.google.com/docs/auth/admin/import-users

## Proxy and scaling boundary

Compose keeps the backend host port on loopback and trusts forwarded client
addresses from its Docker proxy network (`FORWARDED_ALLOW_IPS`). Narrow that value
to your actual proxy address/network when deploying a different topology; never
expose a trusted-forwarding API port directly to untrusted clients. The API is
explicitly single-worker so the in-memory auth limiter is shared by its requests.
Multiple API replicas require a shared/ingress limiter before scaling out.
