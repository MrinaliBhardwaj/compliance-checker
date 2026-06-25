"""
Integration-test DB fixtures.

Default backend is in-memory SQLite so the persist chain is exercised in CI with
no external services. RLS + append-only enforcement are Postgres-only and live in
tests/integration/test_postgres_hardening.py, which skips unless REGIS_TEST_PG_URL
points at a real Postgres.
"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base, Entity, Membership, Organization, User
from app.seed.library_loader import seed_database


@pytest.fixture
def db() -> Session:
    url = os.getenv("REGIS_TEST_DB_URL", "sqlite+pysqlite:///:memory:")
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def seeded_org(db: Session):
    """An org + entity with the full library loaded. Returns (org_id, entity_id)."""
    seed_database(db)
    org = Organization(name="Acme Capital NBFC")
    db.add(org)
    db.flush()
    user = User(email=f"officer-{uuid.uuid4().hex[:8]}@acme.test", full_name="CS Officer")
    db.add(user)
    db.flush()
    # First user is the org's active compliance_admin (mirrors the signup flow).
    db.add(Membership(user_id=user.id, organization_id=org.id,
                      role="compliance_admin", status="active"))
    entity = Entity(organization_id=org.id, legal_name="Acme Capital Ltd", rbi_layer="middle")
    db.add(entity)
    db.flush()
    return {"org_id": org.id, "entity_id": entity.id, "user_id": user.id}
