"""
SQLAlchemy models — 1:1 with the Alembic migrations and the PRD §6 schema.

Import order matters for mapper configuration / Alembic autogenerate: importing
this package registers every model on `Base.metadata`.
"""
from app.models.base import Base
from app.models.calendar import EventListener, HolidayCalendar
from app.models.compliance import CompanyObligation, ObligationInstance
from app.models.content import LawLibrary, ObligationTemplate
from app.models.evidence import Document, DocumentLink
from app.models.legal_updates import LegalUpdate, LegalUpdateStatus
from app.models.profile import CompanyProfile
from app.models.system import AuditLog, CopilotMessage, Notification
from app.models.tenancy import Entity, Location, Membership, Organization, User

__all__ = [
    "Base",
    "Organization", "Entity", "Location", "User", "Membership",
    "LawLibrary", "ObligationTemplate",
    "CompanyObligation", "ObligationInstance",
    "CompanyProfile",
    "Document", "DocumentLink",
    "LegalUpdate", "LegalUpdateStatus",
    "AuditLog", "Notification", "CopilotMessage",
    "HolidayCalendar", "EventListener",
]
