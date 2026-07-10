"""
Evidence service: upload -> (AI) process -> human-confirmed link -> completeness.

The deterministic engine (validation, dedupe, completeness) is the spine; OCR/LLM
classification is an optional seam (no key -> document parked `unprocessed` for
manual classification, everything else still works). AI only SUGGESTS; a human
confirms every link, and completion is gated on primary evidence (Maker-Checker).
"""
from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.storage import get_storage
from app.engines.document_intelligence import (
    classify_and_extract,
    completeness,
    dedupe,
    file_hash,
    validate,
)
from app.models.compliance import CompanyObligation, ObligationInstance
from app.models.content import ObligationTemplate
from app.models.evidence import Document, DocumentLink
from app.models.tenancy import Entity


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _key_from_url(file_url: str) -> str:
    if file_url.startswith("file://"):
        return file_url[len("file://"):]
    if file_url.startswith("s3://"):
        return file_url.split("/", 3)[3]  # s3://bucket/<key>
    return file_url


def _doc_tuple(doc: Document) -> dict:
    return {"id": str(doc.id), "sha256": doc.sha256, "entity_id": str(doc.entity_id),
            "ai_extracted": doc.ai_extracted or {}}


def _org_master(session: Session, entity_id) -> dict:
    entity = session.get(Entity, entity_id) if entity_id else None
    if not entity:
        return {}
    # Entity holds CIN/PAN (field-encrypted); TAN/GSTIN are not modelled in V1.
    return {"cin": entity.cin, "pan": entity.pan, "gstin": None, "tan": None}


def _template_for_instance(session: Session, inst: ObligationInstance) -> ObligationTemplate | None:
    co = session.get(CompanyObligation, inst.company_obligation_id)
    return session.get(ObligationTemplate, co.template_id) if co else None


def _linked_doc_types(session: Session, instance_id) -> list[str]:
    rows = session.execute(
        select(Document.ai_doc_type)
        .join(DocumentLink, DocumentLink.document_id == Document.id)
        .where(DocumentLink.obligation_instance_id == instance_id)
    ).scalars().all()
    return [t for t in rows if t]


def completeness_for_instance(session: Session, inst: ObligationInstance) -> dict:
    tpl = _template_for_instance(session, inst)
    if not tpl:
        return {"required": [], "covered": [], "missing": [], "pct": 0,
                "primary_present": False, "eligible_for_completion": False}
    tpl_dict = {"required_evidence": tpl.required_evidence or []}
    return completeness(tpl_dict, _linked_doc_types(session, inst.id))


# ---------------------------------------------------------------------------
# upload + process
# ---------------------------------------------------------------------------
def upload_document(session: Session, *, organization_id, entity_id, uploaded_by,
                    file_name: str, mime: str, content: bytes,
                    run_processing: bool = True) -> dict:
    """Store + register a document. Exact byte-duplicates are blocked, not stored."""
    sha = file_hash(content)
    existing = session.execute(
        select(Document).where(Document.organization_id == organization_id)
    ).scalars().all()
    verdict = dedupe({"sha256": sha, "entity_id": str(entity_id) if entity_id else None,
                      "ai_extracted": {}},
                     [_doc_tuple(d) for d in existing])
    if verdict["verdict"] == "EXACT_DUPLICATE":
        audit.record(session, action="document_upload_blocked", organization_id=organization_id,
                     actor_user_id=uploaded_by, entity_type="document", entity_id=verdict["of"],
                     meta={"reason": "exact_duplicate", "sha256": sha})
        return {"document": None, "duplicate": verdict}

    doc_id = uuid.uuid4()
    key = f"{organization_id}/{entity_id or 'org'}/{doc_id}/{file_name}"
    url = get_storage().put(key, content, mime)
    doc = Document(id=doc_id, organization_id=organization_id, entity_id=entity_id,
                   uploaded_by=uploaded_by, file_url=url, file_name=file_name,
                   mime_type=mime, sha256=sha, processing_status="processing", ai_extracted={})
    session.add(doc)
    session.flush()
    audit.record(session, action="document_uploaded", organization_id=organization_id,
                 actor_user_id=uploaded_by, entity_type="document", entity_id=str(doc.id),
                 meta={"file_name": file_name, "sha256": sha, "size": len(content), "mime": mime})

    if run_processing:
        process_document(session, doc, content)
    return {"document": doc, "duplicate": verdict if verdict["verdict"] != "UNIQUE" else None}


def process_document(session: Session, doc: Document, content: bytes | None = None) -> Document:
    """Run the AI seam (OCR+LLM). No provider -> park `unprocessed` for manual classify."""
    if content is None:
        content = get_storage().get(_key_from_url(doc.file_url))
    try:
        result = classify_and_extract(content, doc.mime_type or "", hint=None)
    except Exception as e:  # no key / OCR/LLM failure -> manual, never blocks
        doc.processing_status = "unprocessed"
        audit.record(session, action="document_unprocessed", organization_id=doc.organization_id,
                     entity_type="document", entity_id=str(doc.id), meta={"reason": str(e)[:200]})
        return doc

    fields = result.get("fields", {}) or {}
    extracted = {k: (v.get("value") if isinstance(v, dict) else v) for k, v in fields.items()}
    doc.ai_doc_type = result.get("doc_type")
    doc.ai_extracted = extracted
    vu = extracted.get("valid_until")
    if isinstance(vu, str):
        try:
            doc.expiry_date = date.fromisoformat(vu)
        except ValueError:
            pass
    doc.processing_status = "done"
    audit.record(session, action="document_classified", organization_id=doc.organization_id,
                 entity_type="document", entity_id=str(doc.id),
                 meta={"doc_type": doc.ai_doc_type,
                       "classification_confidence": result.get("classification_confidence"),
                       "model_version": "doc-intel-v1"})
    return doc


def classify_manually(session: Session, *, doc: Document, doc_type: str,
                      extracted: dict, actor_user_id) -> Document:
    """Human classification path (the MANUAL route, or correcting an AI suggestion)."""
    doc.ai_doc_type = doc_type
    doc.ai_extracted = extracted or {}
    vu = (extracted or {}).get("valid_until")
    if isinstance(vu, str):
        try:
            doc.expiry_date = date.fromisoformat(vu)
        except ValueError:
            pass
    doc.processing_status = "done"
    audit.record(session, action="document_classified_manual", organization_id=doc.organization_id,
                 actor_user_id=actor_user_id, entity_type="document", entity_id=str(doc.id),
                 meta={"doc_type": doc_type})
    return doc


# ---------------------------------------------------------------------------
# link (human-confirmed) + validation
# ---------------------------------------------------------------------------
def link_document(session: Session, *, organization_id, document_id, instance_id,
                  confirmed_by, role: str, override: bool = False,
                  override_reason: str | None = None) -> dict:
    """Validate the document against the target instance, then link (human-confirmed)."""
    doc = session.get(Document, document_id)
    inst = session.get(ObligationInstance, instance_id)
    if not doc or str(doc.organization_id) != str(organization_id):
        return {"error": "document_not_found"}
    if not inst or str(inst.organization_id) != str(organization_id):
        return {"error": "instance_not_found"}

    # preparers may only attach evidence to their own assigned instances
    if role == "preparer" and str(inst.owner_user_id) != str(confirmed_by):
        return {"error": "forbidden"}

    tpl = _template_for_instance(session, inst)
    co = session.get(CompanyObligation, inst.company_obligation_id)
    tpl_dict = {"form_reference": tpl.form_reference if tpl else None,
                "required_evidence": (tpl.required_evidence if tpl else []) or []}
    inst_dict = {"period_label": inst.period_label,
                 "due_date": inst.due_date.isoformat() if inst.due_date else None}
    checks = validate(doc.ai_extracted or {}, inst_dict, tpl_dict,
                      _org_master(session, co.entity_id if co else None))
    checks_out = [asdict(c) for c in checks]

    # entity mismatch is a hard block (wrong entity's document) unless overridden
    entity_fail = any(c.name == "entity_match" and c.result == "fail" for c in checks)
    if entity_fail and not override:
        audit.record(session, action="document_link_blocked", organization_id=organization_id,
                     actor_user_id=confirmed_by, entity_type="document_link",
                     entity_id=str(document_id),
                     meta={"reason": "entity_match_fail", "instance_id": str(instance_id)})
        return {"blocked": True, "reason": "entity_match_fail", "checks": checks_out}

    existing = session.execute(
        select(DocumentLink).where(DocumentLink.document_id == document_id,
                                   DocumentLink.obligation_instance_id == instance_id)
    ).scalar_one_or_none()
    if existing is None:
        session.add(DocumentLink(document_id=document_id, obligation_instance_id=instance_id,
                                 confirmed_by=confirmed_by))
        session.flush()

    comp = completeness_for_instance(session, inst)
    audit.record(session, action="document_linked", organization_id=organization_id,
                 actor_user_id=confirmed_by, entity_type="document_link",
                 entity_id=str(document_id),
                 meta={"instance_id": str(instance_id), "override": override,
                       "override_reason": override_reason,
                       "checks": {c["name"]: c["result"] for c in checks_out},
                       "completeness_pct": comp["pct"]})
    return {"blocked": False, "checks": checks_out, "completeness": comp}
