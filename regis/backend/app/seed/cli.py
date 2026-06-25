"""
Seed CLI: load the obligation library into the configured database.

    python -m app.seed.cli            # upsert laws + templates (idempotent)
    python -m app.seed.cli --stats    # print library stats without writing
"""
from __future__ import annotations

import argparse

from app.seed.library_loader import library_stats, load_library, seed_database


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the NBFC obligation library.")
    parser.add_argument("--stats", action="store_true", help="print stats and exit")
    args = parser.parse_args()

    lib = load_library()
    stats = library_stats(lib)
    print(f"Library: {stats['laws']} laws, {stats['templates']} templates, "
          f"{stats['due_rule_types']} due-rule types")
    print(f"  verification: {stats['by_verification']}")
    if args.stats:
        return

    from app.core.db import SessionLocal
    with SessionLocal() as session:
        written = seed_database(session)
        session.commit()
    print(f"Seeded: {written['laws']} laws, {written['templates']} templates "
          f"(idempotent upsert; all DRAFT_UNVERIFIED).")


if __name__ == "__main__":
    main()
