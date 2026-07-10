"""
Database engine, session factory, and the tenant-scoping RLS context.

RLS model: every request sets a session-local GUC `app.current_org` (the caller's
organization_id). Postgres RLS policies (installed by migration) restrict every
tenant table to rows matching that GUC. The GUC is set per-transaction so a
connection returned to the pool never leaks another tenant's scope.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_settings = get_settings()
engine = create_engine(_settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)

_IS_PG = engine.dialect.name == "postgresql"


def set_tenant(session: Session, organization_id: str | None) -> None:
    """Set the RLS GUC for this session's transaction (Postgres only)."""
    if not _IS_PG:
        return  # SQLite test path: RLS enforced in Postgres only
    session.execute(
        text("SELECT set_config('app.current_org', :org, true)"),
        {"org": str(organization_id) if organization_id else ""},
    )


def set_bootstrap(session: Session) -> None:
    """Grant this transaction the pre-tenant *bootstrap* scope.

    Login must resolve which org a user belongs to *before* any tenant scope
    exists, so it needs to read `memberships` across the RLS boundary. Only the
    memberships policy honours this GUC (read-only), and the sole caller filters
    by user identity — so this never returns unbounded tenant data. Postgres-only.
    """
    if not _IS_PG:
        return
    session.execute(text("SELECT set_config('app.bootstrap', 'on', true)"))


@contextmanager
def tenant_session(organization_id: str | None) -> Iterator[Session]:
    """A session bound to one tenant for its lifetime; commits on success."""
    session = SessionLocal()
    try:
        set_tenant(session, organization_id)
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
