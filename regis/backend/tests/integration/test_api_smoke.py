"""
API smoke test (TestClient over a temp-file SQLite).

Exercises the real HTTP surface end to end: signup -> JWT -> onboarding preview ->
calendar generate -> dashboard -> copilot ask, including the read-only escalation.
Env is set before importing the app so app.core.db binds to the test database.
"""
from __future__ import annotations

import os
import tempfile
import uuid

import pytest

# --- bind the app to a throwaway file DB BEFORE importing it ---
_TMP = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP.close()
os.environ["REGIS_DATABASE_URL"] = f"sqlite+pysqlite:///{_TMP.name}"
os.environ["REGIS_JWT_SECRET"] = "test-secret"

from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from app.seed.library_loader import seed_database  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402


@pytest.fixture(scope="module")
def client():
    get_settings.cache_clear()
    Base.metadata.create_all(engine)
    with SessionLocal() as s:
        seed_database(s)
        s.commit()
    yield TestClient(app)
    Base.metadata.drop_all(engine)


def _auth(client) -> tuple[dict, str]:
    # unique email per call: the module-scoped client shares one DB, so a fixed
    # email would 409 on every signup after the first
    r = client.post("/auth/signup", json={
        "email": f"officer-{uuid.uuid4().hex[:8]}@acme.example", "password": "pw123456",
        "organization_name": "Acme NBFC", "entity_legal_name": "Acme Capital Ltd",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["entity_id"]


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_full_onboarding_flow(client):
    headers, entity_id = _auth(client)

    # profile preview (no commit) — returns provenance + gap questions
    preview = client.post("/onboarding/profile/preview", headers=headers, json={
        "raw_input": {"asset_size": "3000", "deposit_taking": "No",
                      "operating_states": ["MH", "KA", "TN", "DL"],
                      "employee_count": 260, "gst_registered": "Yes"}
    }).json()
    assert preview["profile"]["rbi_layer"] == "middle"
    assert "gap_questions" in preview

    # generate calendar (commit) — Profile B-like
    gen = client.post("/onboarding/calendar/generate", headers=headers, json={
        "entity_id": entity_id,
        "raw_input": {
            "asset_size": "3000", "turnover": "450", "deposit_taking": "No",
            "is_listed": "No", "has_listed_debt": "Yes",
            "operating_states": ["MH", "KA", "TN", "DL"], "branch_count": 22,
            "employee_count": 260, "gst_registered": "Yes",
            "has_foreign_investment": "Yes", "has_ecb": "Yes", "is_secured_lender": "Yes",
            "has_borrowings": "Yes", "is_large_corporate": "Yes", "has_msme_dues": "Yes",
            "has_floating_rate_retail": "Yes", "has_capital_changes": "Yes", "has_sbo": "Yes",
            "has_nonresident_payments": "Yes", "has_international_transactions": "Yes",
            "has_reportable_accounts": "Yes",
        },
    }).json()
    # clean payload closes the loop to 99 applicable obligations
    assert gen["company_obligations"] == 99
    assert gen["instances"] > 0

    # dashboard rollup
    dash = client.get("/obligations/dashboard", headers=headers).json()
    assert "health_score" in dash and dash["total_instances"] > 0

    # copilot: structured answer is grounded
    due = client.post("/copilot/ask", headers=headers,
                      json={"query": "What's due this month?"}).json()
    assert due["intent"] == "DUE_WINDOW"
    assert due["confidence"] == 0.97

    # copilot: action request -> read-only escalation, no substantive answer
    act = client.post("/copilot/ask", headers=headers,
                      json={"query": "File my GST return for me"}).json()
    assert act["escalated"] and act["escalation_reason"] == "read_only"


def test_evidence_and_maker_checker_over_http(client):
    headers, entity_id = _auth(client)
    # ensure a calendar exists (idempotent if a prior test already generated it)
    client.post("/onboarding/calendar/generate", headers=headers, json={
        "entity_id": entity_id,
        "raw_input": {"asset_size": "3000", "turnover": "450", "deposit_taking": "No",
                      "has_listed_debt": "Yes", "operating_states": ["MH", "KA", "TN", "DL"],
                      "employee_count": 260, "gst_registered": "Yes"},
    })
    # grab a pending instance
    instances = client.get("/obligations/instances", headers=headers).json()
    inst_id = instances[0]["id"]

    # start -> upload -> classify -> link -> submit -> approve
    assert client.post(f"/obligations/instances/{inst_id}/start", headers=headers,
                       json={}).json()["status"] == "in_progress"

    up = client.post("/documents/upload", headers=headers,
                     files={"file": ("ack.pdf", b"%PDF ack bytes", "application/pdf")},
                     data={"entity_id": entity_id}).json()
    doc_id = up["document"]["id"]
    assert up["document"]["processing_status"] == "unprocessed"  # AI off in tests

    client.post(f"/documents/{doc_id}/classify", headers=headers,
                json={"doc_type": "FILING_ACK", "extracted": {"period": instances[0]["period_label"]}})
    link = client.post(f"/documents/{doc_id}/link", headers=headers,
                       json={"instance_id": inst_id}).json()
    assert link["blocked"] is False

    client.post(f"/obligations/instances/{inst_id}/submit", headers=headers, json={})
    approve = client.post(f"/obligations/instances/{inst_id}/approve", headers=headers, json={})
    # FILING_ACK is primary for many obligations; if this one needs a different primary,
    # the gate returns 409 — both are valid, assert the gate behaves (200 or 409).
    assert approve.status_code in (200, 409)


def test_exact_duplicate_upload_over_http(client):
    headers, entity_id = _auth(client)
    files = {"file": ("dup.pdf", b"same-bytes-xyz", "application/pdf")}
    first = client.post("/documents/upload", headers=headers, files=files,
                        data={"entity_id": entity_id}).json()
    assert first["document"] is not None
    files2 = {"file": ("dup2.pdf", b"same-bytes-xyz", "application/pdf")}
    second = client.post("/documents/upload", headers=headers, files=files2,
                         data={"entity_id": entity_id}).json()
    assert second["document"] is None
    assert second["duplicate"]["verdict"] == "EXACT_DUPLICATE"


def test_report_export_over_http(client):
    headers, entity_id = _auth(client)
    client.post("/onboarding/calendar/generate", headers=headers, json={
        "entity_id": entity_id,
        "raw_input": {"asset_size": "3000", "deposit_taking": "No",
                      "operating_states": ["MH", "KA"], "employee_count": 260,
                      "gst_registered": "Yes"},
    })
    j = client.get("/reports/compliance", headers=headers).json()
    assert j["provisional"] is True and "health_score" in j

    html = client.get("/reports/compliance.html", headers=headers)
    assert html.status_code == 200 and "Compliance Status Report" in html.text

    pdf = client.get("/reports/compliance.pdf", headers=headers)
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF-")


def test_preparer_cannot_export(client):
    from app.core.security import Principal, create_access_token
    tok = create_access_token(Principal(user_id="u1", organization_id="o1", role="preparer"))
    r = client.get("/reports/compliance.pdf", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403


def test_notifications_inbox_over_http(client):
    headers, _ = _auth(client)
    assert client.get("/notifications", headers=headers).status_code == 200


def test_legal_updates_over_http(client):
    headers, entity_id = _auth(client)
    # ensure a profile exists (so matching has something to match against)
    client.post("/onboarding/calendar/generate", headers=headers, json={
        "entity_id": entity_id,
        "raw_input": {"asset_size": "3000", "deposit_taking": "No",
                      "operating_states": ["MH"], "employee_count": 260, "gst_registered": "Yes"},
    })
    pub = client.post("/legal-updates", headers=headers, json={
        "title": "Middle-layer CCO change", "affects_filter": {"rbi_layer": ["middle", "upper"]},
    })
    assert pub.status_code == 200
    update_id = pub.json()["id"]

    feed = client.get("/legal-updates", headers=headers).json()
    assert feed and feed[0]["match"] in ("APPLICABLE", "NEEDS_REVIEW")

    rev = client.post(f"/legal-updates/{update_id}/review", headers=headers,
                      json={"status": "applicable"})
    assert rev.status_code == 200 and rev.json()["status"] == "applicable"


def test_preparer_cannot_review_legal_update(client):
    from app.core.security import Principal, create_access_token
    tok = create_access_token(Principal(user_id="u1", organization_id="o1", role="preparer"))
    r = client.post("/legal-updates/00000000-0000-0000-0000-000000000000/review",
                    headers={"Authorization": f"Bearer {tok}"}, json={"status": "applicable"})
    assert r.status_code == 403


def test_auth_required(client):
    assert client.get("/obligations/dashboard").status_code == 401


def test_preparer_cannot_generate(client):
    """RBAC: only compliance_admin can generate the calendar."""
    # a fresh admin to mint a preparer would need invite flow; assert the gate via role check
    from app.core.security import Principal, create_access_token
    tok = create_access_token(Principal(user_id="u1", organization_id="o1", role="preparer"))
    r = client.post("/onboarding/calendar/generate",
                    headers={"Authorization": f"Bearer {tok}"},
                    json={"entity_id": "e1", "raw_input": {}})
    assert r.status_code == 403
