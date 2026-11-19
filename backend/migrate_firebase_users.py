"""Explicit, restartable migration of local accounts to Firebase; no emails sent.

Run --dry-run first, then --apply. Standard scrypt password hashes are imported without exposing plaintext passwords.
Unverified password users must verify their email before accessing the app.
"""
import argparse
from backend.accounts import accounts
from backend.firebase_auth import admin_app


def migrate(apply=False):
    from firebase_admin import auth
    app = admin_app()
    with accounts.transaction() as sql:
        rows = sql('SELECT u.*,g.subject FROM app_users u LEFT JOIN google_identities g ON g.user_id=u.id').fetchall()
    planned = []
    seen = set()
    # Validate every collision before creating anything in Firebase.
    for row in rows:
        user = dict(row)
        if user['id'] in seen:
            raise RuntimeError('An account has multiple Google identities. Resolve its provider mapping before migration.')
        seen.add(user['id'])
        try:
            remote = auth.get_user_by_email(user['email'], app=app)
        except auth.UserNotFoundError:
            remote = None
        if remote and remote.uid != user['id']:
            raise RuntimeError('Firebase already has an account with a conflicting email. Resolve the identity conflict before migration; no automatic email linking is performed.')
        try:
            uid_record = auth.get_user(user['id'], app=app)
        except auth.UserNotFoundError:
            uid_record = None
        if uid_record and uid_record.email != user['email']:
            raise RuntimeError('A Firebase UID conflicts with a local account. Resolve it before migration.')
        planned.append((user, remote))
    print(f'{len(planned)} accounts checked. Existing local IDs and all campaign/friend records will be preserved.')
    if not apply:
        print('Dry run only. Use --apply to create Firebase identities. No email is sent by migration.')
        return
    for user, remote in planned:
        if remote is None:
            providers = []
            if user['subject']:
                providers.append(auth.UserProvider(uid=user['subject'], provider_id='google.com', email=user['email']))
            salt, digest = user['password_hash'].split(':')
            record = auth.ImportUserRecord(uid=user['id'], email=user['email'], display_name=user['name'],
                email_verified=False, provider_data=providers,
                password_hash=bytes.fromhex(digest), password_salt=bytes.fromhex(salt))
            hashing = auth.UserImportHash.standard_scrypt(memory_cost=2**14, parallelization=1, block_size=8, derived_key_length=64)
            result = auth.import_users([record], hash_alg=hashing, app=app)
            if result.failure_count:
                raise RuntimeError('Firebase import failed. Migration can be rerun after resolving the project configuration.')
        with accounts.transaction() as sql:
            existing = sql('SELECT uid FROM firebase_identities WHERE user_id=%s', (user['id'],)).fetchone()
            if existing and existing['uid'] != user['id']:
                raise RuntimeError('Local account already maps to a different Firebase identity.')
            sql('INSERT INTO firebase_identities(uid,user_id) VALUES (%s,%s) ON CONFLICT(uid) DO NOTHING', (user['id'], user['id']))
    print('Migration complete. Password users retain their passwords and must verify email; Google users retain their provider identity.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--dry-run', action='store_true')
    group.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    migrate(apply=args.apply)
