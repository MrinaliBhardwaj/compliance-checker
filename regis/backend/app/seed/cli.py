"""
Seed CLI: load the obligation library into the configured database.

    python -m app.seed.cli                 # upsert laws + templates (idempotent)
    python -m app.seed.cli --create-all    # create the tables first, then seed
    python -m app.seed.cli --stats         # print library stats without writing

`--create-all` is the SQLite quickstart path: on a brand-new database file there
are no tables yet, and seeding died with "no such table: law_library" — which
reads like a broken build rather than a missing step. Postgres still gets its
schema from Alembic; create_all is only ever a dev convenience.
"""
from __future__ import annotations

import argparse

from app.seed.library_loader import library_stats, load_library, seed_database


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the NBFC obligation library.")
    parser.add_argument("--stats", action="store_true", help="print stats and exit")
    parser.add_argument("--create-all", action="store_true",
                        help="create any missing tables before seeding (dev/SQLite)")
    args = parser.parse_args()

    lib = load_library()
    stats = library_stats(lib)
    print(f"Library: {stats['laws']} laws, {stats['templates']} templates, "
          f"{stats['due_rule_types']} due-rule types")
    print(f"  verification: {stats['by_verification']}")
    if args.stats:
        return

    from app.core.db import SessionLocal, engine

    if args.create_all:
        from app.models import Base
        Base.metadata.create_all(engine)
        print(f"Schema: ensured {len(Base.metadata.tables)} tables exist.")

    with SessionLocal() as session:
        written = seed_database(session)
        session.commit()
    print(f"Seeded: {written['laws']} laws, {written['templates']} templates "
          f"(idempotent upsert; all DRAFT_UNVERIFIED).")


if __name__ == "__main__":
    main()
