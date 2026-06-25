"""Request-scoped dependencies: a DB session with the caller's tenant RLS scope set."""
from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.db import SessionLocal, set_tenant
from app.core.security import CurrentPrincipal


def get_db(principal: CurrentPrincipal) -> Iterator[Session]:
    """Yield a session pinned to the caller's org (sets the RLS GUC)."""
    session = SessionLocal()
    try:
        set_tenant(session, principal.organization_id)
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


DbSession = Annotated[Session, Depends(get_db)]
