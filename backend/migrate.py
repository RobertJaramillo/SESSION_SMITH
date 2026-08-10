"""Apply versioned SQL migrations.

Run from the repository root after `docker compose up -d db`:
    backend/.venv/bin/python -m backend.migrate
"""

from __future__ import annotations

from pathlib import Path

from backend.db import connect

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def apply_migrations() -> list[str]:
    """Apply each unapplied *.sql migration once, in filename order."""
    applied_now: list[str] = []
    with connect(autocommit=True) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename text PRIMARY KEY,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        applied = {row["filename"] for row in connection.execute("SELECT filename FROM schema_migrations").fetchall()}
        for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if migration.name in applied:
                continue
            with connection.transaction():
                connection.execute(migration.read_text())
                connection.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (migration.name,))
            applied_now.append(migration.name)
    return applied_now


def main() -> None:
    applied = apply_migrations()
    if applied:
        print("Applied migrations:")
        print("\n".join(f"  {name}" for name in applied))
    else:
        print("Database schema is already up to date.")


if __name__ == "__main__":
    main()
