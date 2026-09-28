"""
Regulatory Activity (spec §15) — the generic entity that Submission
Builder, Sequence Management, and Response Center will attach to in
later layers. Regulatory Event (spec §16) is a business-facing
timeline, distinct from the security/compliance-oriented AuditEvent —
every RegulatoryEvent write is paired with an AuditEvent write (see
services/regulatory_event_service.py), never a replacement for one.
"""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Enum, ForeignKey, String, Text, Date, DateTime
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import AuditFieldsMixin, TimestampMixin, UUIDPKMixin


class RegulatoryActivityType(str, enum.Enum):
    INITIAL_SUBMISSION = "INITIAL_SUBMISSION"
    VARIATION = "VARIATION"
    RENEWAL = "RENEWAL"
    SUPPLEMENT = "SUPPLEMENT"
    RESPONSE = "RESPONSE"
    DEFICIENCY = "DEFICIENCY"
    POST_APPROVAL_CHANGE = "POST_APPROVAL_CHANGE"
    OTHER = "OTHER"


class RegulatoryActivityStatus(str, enum.Enum):
    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class RegulatoryActivity(UUIDPKMixin, TimestampMixin, AuditFieldsMixin, Base):
    __tablename__ = "regulatory_activities"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    regulatory_application_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("regulatory_applications.id", ondelete="SET NULL"), nullable=True, index=True
    )
    dossier_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dossiers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    authority_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("regulatory_authorities.id", ondelete="RESTRICT"), nullable=False
    )
    activity_type: Mapped[RegulatoryActivityType] = mapped_column(
        Enum(RegulatoryActivityType, name="regulatory_activity_type"), nullable=False
    )
    status: Mapped[RegulatoryActivityStatus] = mapped_column(
        Enum(RegulatoryActivityStatus, name="regulatory_activity_status"),
        default=RegulatoryActivityStatus.PLANNED,
        nullable=False,
        index=True,
    )
    planned_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    activity_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)


class RegulatoryEventType(str, enum.Enum):
    DOSSIER_CREATED = "DOSSIER_CREATED"
    DOSSIER_STATUS_CHANGED = "DOSSIER_STATUS_CHANGED"
    DOCUMENT_ADDED = "DOCUMENT_ADDED"
    DOCUMENT_REVISED = "DOCUMENT_REVISED"
    REVIEW_STARTED = "REVIEW_STARTED"
    REVIEW_COMPLETED = "REVIEW_COMPLETED"
    ACTIVITY_CREATED = "ACTIVITY_CREATED"
    ACTIVITY_STATUS_CHANGED = "ACTIVITY_STATUS_CHANGED"
    SUBMISSION_CREATED = "SUBMISSION_CREATED"  # placeholder value; no Submission entity until a later layer
    SUBMISSION_LOCKED = "SUBMISSION_LOCKED"
    QUERY_RECEIVED = "QUERY_RECEIVED"
    RESPONSE_SUBMITTED = "RESPONSE_SUBMITTED"
    # --- Layer 3 additions ---
    INTELLIGENCE_PUBLISHED = "INTELLIGENCE_PUBLISHED"
    INTELLIGENCE_STATUS_CHANGED = "INTELLIGENCE_STATUS_CHANGED"
    INTELLIGENCE_DISTRIBUTED = "INTELLIGENCE_DISTRIBUTED"


class RegulatoryEvent(UUIDPKMixin, Base):
    __tablename__ = "regulatory_events"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    event_type: Mapped[RegulatoryEventType] = mapped_column(
        Enum(RegulatoryEventType, name="regulatory_event_type"), nullable=False
    )
    dossier_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=True, index=True
    )
    regulatory_activity_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("regulatory_activities.id", ondelete="CASCADE"), nullable=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    # Layer 3 addition — nullable FK, additive, same pattern as
    # Document.document_type and Organization.organization_type. Not a
    # new event system: same table, same audit pairing convention.
    intelligence_item_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("regulatory_intelligence_items.id", ondelete="CASCADE"), nullable=True, index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
