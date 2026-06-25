"""
Evidence API: upload (multipart) -> classify (AI or manual) -> link (confirmed) ->
completeness. AI suggests; the human confirms the link; completion is gated
elsewhere (Maker-Checker). All rows are org-scoped (RLS) and audited.
"""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select

from app.core.deps import DbSession
from app.core.security import CurrentPrincipal
from app.models.evidence import Document
from app.modules.documents import service as svc

router = APIRouter(prefix="/documents", tags=["documents"])


def _doc_out(d: Document) -> dict:
    return {"id": str(d.id), "file_name": d.file_name, "mime_type": d.mime_type,
            "ai_doc_type": d.ai_doc_type, "ai_extracted": d.ai_extracted,
            "processing_status": d.processing_status,
            "expiry_date": d.expiry_date.isoformat() if d.expiry_date else None}


@router.post("/upload")
async def upload(db: DbSession, principal: CurrentPrincipal,
                 file: UploadFile = File(...), entity_id: str = Form(...)) -> dict:
    content = await file.read()
    result = svc.upload_document(
        db, organization_id=principal.organization_id, entity_id=entity_id,
        uploaded_by=principal.user_id, file_name=file.filename or "upload.bin",
        mime=file.content_type or "application/octet-stream", content=content)
    if result["document"] is None:
        # exact duplicate -> blocked, offer the existing doc
        return {"duplicate": result["duplicate"], "document": None}
    return {"document": _doc_out(result["document"]), "duplicate": result["duplicate"]}


class ClassifyBody(BaseModel):
    doc_type: str
    extracted: dict = {}


@router.post("/{document_id}/classify")
def classify(document_id: str, body: ClassifyBody, db: DbSession,
             principal: CurrentPrincipal) -> dict:
    doc = db.get(Document, document_id)
    if not doc or str(doc.organization_id) != principal.organization_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    svc.classify_manually(db, doc=doc, doc_type=body.doc_type, extracted=body.extracted,
                          actor_user_id=principal.user_id)
    return _doc_out(doc)


class LinkBody(BaseModel):
    instance_id: str
    override: bool = False
    override_reason: str | None = None


@router.post("/{document_id}/link")
def link(document_id: str, body: LinkBody, db: DbSession,
         principal: CurrentPrincipal) -> dict:
    res = svc.link_document(
        db, organization_id=principal.organization_id, document_id=document_id,
        instance_id=body.instance_id, confirmed_by=principal.user_id,
        role=principal.role, override=body.override, override_reason=body.override_reason)
    if res.get("error") == "forbidden":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your assigned obligation")
    if res.get("error"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, res["error"])
    if res.get("blocked"):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            {"reason": res["reason"], "checks": res["checks"]})
    return res


@router.get("")
def list_documents(db: DbSession, principal: CurrentPrincipal) -> list[dict]:
    rows = db.execute(
        select(Document).where(Document.organization_id == principal.organization_id)
        .order_by(Document.created_at.desc())
    ).scalars().all()
    return [_doc_out(d) for d in rows]
