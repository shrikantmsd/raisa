"""
Dossier — first-class entity with a controlled lifecycle (Layer 2 spec
§4, §14). State transitions go through
`services.dossier_service.transition_status`, never a direct field
assignment from a route handler, so every transition is authorized and
audited in one place (mirroring how Layer 1 centralized `authorize()`).
"""
import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import AuditFieldsMixin, TimestampMixin, UUIDPKMixin


class DossierStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    UNDER_REVIEW = "UNDER_REVIEW"
    ACTIVE = "ACTIVE"
    LOCKED = "LOCKED"
    ARCHIVED = "ARCHIVED"


# Explicit allowed-transition map (spec §4: "controlled state
# transitions rather than unrestricted status changes"). Anything not
# listed here is rejected by dossier_service.transition_status
# regardless of the caller's permissions — RBAC decides WHO may attempt
# a transition; this map decides WHICH transitions exist at all.
ALLOWED_DOSSIER_TRANSITIONS: dict[DossierStatus, set[DossierStatus]] = {
    DossierStatus.DRAFT: {DossierStatus.UNDER_REVIEW, DossierStatus.ARCHIVED},
    DossierStatus.UNDER_REVIEW: {DossierStatus.ACTIVE, DossierStatus.DRAFT, DossierStatus.ARCHIVED},
    DossierStatus.ACTIVE: {DossierStatus.LOCKED, DossierStatus.UNDER_REVIEW, DossierStatus.ARCHIVED},
    DossierStatus.LOCKED: {DossierStatus.ACTIVE, DossierStatus.ARCHIVED},
    DossierStatus.ARCHIVED: set(),  # terminal
}


class Dossier(UUIDPKMixin, TimestampMixin, AuditFieldsMixin, Base):
    __tablename__ = "dossiers"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    regulatory_application_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("regulatory_applications.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    authority_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("regulatory_authorities.id", ondelete="RESTRICT"), nullable=False
    )
    region: Mapped[str] = mapped_column(String(64), nullable=False)
    ctd_standard: Mapped[str] = mapped_column(String(32), default="eCTD", nullable=False)
    standard_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[DossierStatus] = mapped_column(
        Enum(DossierStatus, name="dossier_status"), default=DossierStatus.DRAFT, nullable=False, index=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    dossier_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON-encoded, freeform for Layer 2
