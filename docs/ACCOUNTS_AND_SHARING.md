# Accounts and campaign sharing

The real API now requires sign-in. Register using a display name, email and a
password of at least 12 characters. Email addresses are normalized to lowercase.
Account settings persist display names, emails and password changes; changing an
email or password requires the current password and revokes other sessions.

The dashboard shows campaigns you own and campaigns you have explicitly joined.
The campaign tile names its owner and your role. Friendship does not grant access
to campaigns. Removing a friend does not revoke an existing campaign membership;
owners remove campaign members separately in Campaign Settings.

## Friends and invitations

Open **Friends & invitations** on the dashboard to send a friend request by an
existing account's email. The recipient can accept or decline; senders can cancel
pending requests, and either party can remove an accepted friendship.

Owners use **Campaign Settings → Owner & members** to invite an accepted friend
or any email address as a player or viewer. Invitations last seven days, can be
revoked, and remain pending until the recipient accepts. People without accounts
can register later with the invited email and find the invitation on their
dashboard. Invitations are in-app: this version does not send email or generate
public bearer links. Tell the invitee which email address to use.

| Role | Access |
| --- | --- |
| Owner | Full campaign management, private GM notes, AI jobs, canon review, invitations and membership management |
| Player | Campaign summary, member list and approved canon, read-only |
| Viewer | Campaign summary, member list and approved canon, read-only |

Player character contribution is future work. Neither player nor viewer can read
raw notes, worldbuilding inputs, pending proposals, prep, exports or job history.
Owners cannot be removed or assigned through invitations. Ownership transfer is
not exposed in this version.

## Persistence and rollout

Apply migration `007_accounts_and_sharing.sql` using `python -m backend.migrate`
before starting the updated API. The normal `./run` startup does this automatically.
PostgreSQL persists users, hashed passwords, sessions, friendships, memberships and
invitations. Without `DATABASE_URL`, accounts/sharing use SQLite in memory and
campaigns use the existing development store; both reset when the process stops.

Existing campaigns, including seeds, have no authenticated owner and are hidden
from newly registered accounts. No first registrant automatically acquires legacy
data. An administrator who knows the correct owner can assign a specific campaign
explicitly after registration:

```sql
INSERT INTO campaign_access (campaign_id, user_id, role)
SELECT c.id, u.id, 'owner'
FROM campaigns c CROSS JOIN app_users u
WHERE c.id = 'campaign_to_assign' AND u.email = 'owner@example.com';
```

The unique owner index prevents assigning two owners. New campaigns create their
owner membership in the same PostgreSQL transaction as the campaign itself.

The frontend now connects to FastAPI by default. UI-only mock mode is opt-in with
`VITE_USE_MOCKS=true`; its sample sign-in and preview are not real accounts.

## Sessions and deployment limits

Passwords use salted scrypt hashes; opaque random session tokens are stored only
as SHA-256 digests server-side. Sessions expire after seven days and logout revokes
the session. Cookies use HttpOnly and SameSite=Lax. HTTPS requests set Secure;
behind TLS termination set `SESSION_COOKIE_SECURE=true` on the API service to force
Secure cookies. Browser writes check Origin and Fetch Metadata, and JSON write
endpoints require `application/json`.

Email verification, forgotten-password recovery and OAuth are not implemented.
Email ownership is therefore not verified: use this version in a trusted beta
until verification is added. Login/registration limits are per-process and source
address; deploy a shared ingress rate limiter before scaling API replicas. Trust
forwarded headers only from your own proxy. PostgreSQL stores the social graph
normally, but campaign listing currently filters repository results in Python;
a SQL membership join should replace that when the dataset grows.

## Verification

`python3 -m unittest backend.tests.test_accounts` exercises real registration,
sign-in, cookie sessions, password changes, friendship consent, invitations before
registration, expiry, revocation, membership removal and forbidden campaign, job
and proposal access. It runs in development memory mode or against a migrated
PostgreSQL database specified by `DATABASE_URL`. Frontend interaction tests cover
registration, incoming requests, invitations, and choosing friend/role combinations.
