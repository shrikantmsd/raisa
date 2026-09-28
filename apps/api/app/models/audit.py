"""
AuditEvent — append-oriented audit trail (spec §27).

No update/delete path is exposed anywhere in the service layer for this
table on purpose: audit rows are written once by `audit_service.record`
and never mutated. Visibility is filtered by role in the API layer
(spec §28), not by hiding rows at the database level, so a future
CoLAB Super Admin view can still reach platform-level events.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, String, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import UUIDPKMixin


class AuditEventType(str, enum.Enum):
    USER_CREATED = "USER_CREATED"
    USER_UPDATED = "USER_UPDATED"
    USER_STATUS_CHANGED = "USER_STATUS_CHANGED"
    ROLE_ASSIGNED = "ROLE_ASSIGNED"
    ROLE_REVOKED = "ROLE_REVOKED"
    PERMISSION_CHANGED = "PERMISSION_CHANGED"
    LOGIN = "LOGIN"
    DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED"
    DOCUMENT_VIEWED = "DOCUMENT_VIEWED"
    DOCUMENT_DOWNLOADED = "DOCUMENT_DOWNLOADED"
    DOCUMENT_VERSION_CREATED = "DOCUMENT_VERSION_CREATED"
    THEME_CHANGED = "THEME_CHANGED"
    CONFIGURATION_CHANGED = "CONFIGURATION_CHANGED"
    ORGANIZATION_CREATED = "ORGANIZATION_CREATED"
    AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"
    # --- Layer 3: precise event types for intelligence. Layer 2 reused
    # USER_CREATED/USER_STATUS_CHANGED for Product/Dossier rows (object_type
    # disambiguates); that's left untouched so Layer 2 behavior and tests
    # don't change, but Layer 3 gets correctly-named types so audit
    # queries by event_type ("show me every publication") actually work.
    INTELLIGENCE_CREATED = "INTELLIGENCE_CREATED"
    INTELLIGENCE_UPDATED = "INTELLIGENCE_UPDATED"
    INTELLIGENCE_STATUS_CHANGED = "INTELLIGENCE_STATUS_CHANGED"
    INTELLIGENCE_CLASSIFICATION_CHANGED = "INTELLIGENCE_CLASSIFICATION_CHANGED"
    INTELLIGENCE_DISTRIBUTED = "INTELLIGENCE_DISTRIBUTED"
    INTELLIGENCE_SOURCE_CHANGED = "INTELLIGENCE_SOURCE_CHANGED"


class AuditEvent(UUIDPKMixin, Base):
    __tablename__ = "audit_events"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_type: Mapped[AuditEventType] = mapped_column(Enum(AuditEventType, name="audit_event_type"), nullable=False)
    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    previous_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    session_context: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="api")
