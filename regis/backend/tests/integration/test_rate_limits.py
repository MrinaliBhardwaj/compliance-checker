"""
Integration — API rate limiting beyond the auth endpoints.

Two tiers: a blunt per-IP ceiling across the whole API, and a tighter per-org
limit on the routes that actually cost something (calendar generation writes
~367 rows; upload spends I/O).

The per-org tests assert a **429**, not merely "the route still works". The
dependency's first implementation imported CurrentPrincipal inside the factory;
with `from __future__ import annotations` the annotation is a string FastAPI
resolves against module globals, so it silently degraded to a 422 and enforced
nothing. A test that only checked the happy path would have passed.
"""
from __future__ import annotations

import os
import tempfile

import pytest

# app.core.db binds its engine at import time, and signup deliberately bypasses
# get_db (it must set the RLS GUC before the org exists), so it uses that
# module-level SessionLocal. The env therefore has to be set before the app is
# imported. If a sibling module already bound one, reuse that same file rather
# than pointing the two at different databases.
if "REGIS_DATABASE_URL" not in os.environ:
    _TMP = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    _TMP.close()
    os.environ["REGIS_DATABASE_URL"] = f"sqlite+pysqlite:///{_TMP.name}"
    os.environ["REGIS_JWT_SECRET"] = "test-secret"
_DB_URL = os.environ["REGIS_DATABASE_URL"]

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core import ratelimit  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.deps import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from app.seed.library_loader import seed_database  # noqa: E402


@pytest.fixture(scope="module")
def client():
    """Mirrors the smoke suite: a temp-file engine with get_db overridden."""
    get_settings.cache_clear()
    engine = create_engine(_DB_URL, future=True)
    TestSession = sessionmaker(bind=engine, autoflush=False,
                               expire_on_commit=False, future=True)
    Base.metadata.create_all(engine)
    with TestSession() as s:
        seed_database(s)
        s.commit()

    def _override_get_db():
        session = TestSession()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _clear():
    ratelimit.clear()
    yield
    ratelimit.clear()


def test_expensive_route_is_limited_per_org(client, monkeypatch):
    """Generation is capped per organisation, and says so with Retry-After."""
    monkeypatch.setattr(get_settings(), "expensive_max_requests", 3, raising=False)

    headers, _ = _signed_up(client)
    body = {"profile": _MIN_PROFILE, "window_start": "2026-04-01",
            "window_end": "2027-03-31"}

    seen = [client.post("/onboarding/calendar/generate", headers=headers, json=body)
            .status_code for _ in range(5)]

    assert 429 in seen, f"expected a 429 within 5 calls, saw {seen}"
    limited = next(s for s in seen if s == 429)
    assert limited == 429

    last = client.post("/onboarding/calendar/generate", headers=headers, json=body)
    assert last.status_code == 429
    assert last.headers.get("Retry-After")
    assert "rate limited" in last.json()["detail"].lower()


def test_the_limit_is_scoped_to_the_organisation(client, monkeypatch):
    """One tenant exhausting its budget must not throttle another."""
    monkeypatch.setattr(get_settings(), "expensive_max_requests", 2, raising=False)

    a_headers, _ = _signed_up(client)
    b_headers, _ = _signed_up(client)
    body = {"profile": _MIN_PROFILE, "window_start": "2026-04-01",
            "window_end": "2027-03-31"}

    for _ in range(4):
        client.post("/onboarding/calendar/generate", headers=a_headers, json=body)
    assert client.post("/onboarding/calendar/generate",
                       headers=a_headers, json=body).status_code == 429

    # B has spent nothing; its first call must not be refused.
    assert client.post("/onboarding/calendar/generate",
                       headers=b_headers, json=body).status_code != 429


def test_health_is_never_rate_limited(client, monkeypatch):
    """The load balancer polls it; throttling health removes a healthy task."""
    monkeypatch.setattr(get_settings(), "api_max_requests", 2, raising=False)
    assert all(client.get("/health").status_code == 200 for _ in range(6))


def test_global_ip_limit_applies_to_ordinary_routes(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "api_max_requests", 3, raising=False)
    codes = [client.get("/obligations").status_code for _ in range(6)]
    assert 429 in codes, f"expected the global IP ceiling to fire, saw {codes}"


# ---------------------------------------------------------------------------

_MIN_PROFILE = {
    "rbi_registered": True, "nbfc_category": "nd_si", "rbi_layer": "middle",
    "deposit_taking": False, "asset_size_cr": 3000, "turnover_cr": 450,
    "employee_count": 260, "operating_states": ["MH"], "gst_registered": True,
}


def _signed_up(client) -> tuple[dict, str]:
    """A fresh org + bearer header. Signup itself is not expensive-limited."""
    import uuid
    email = f"rl-{uuid.uuid4().hex[:8]}@acme.example"
    r = client.post("/auth/signup", json={
        "email": email, "password": "goodpassword1",
        "organization_name": f"RL {uuid.uuid4().hex[:6]}",
        "entity_legal_name": "RL Ltd"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, email
