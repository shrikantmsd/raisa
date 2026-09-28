"""
Regulatory Intelligence domain (Layer 3 spec §2-4, §10, §14).

Every row still has a real `organization_id` — global intelligence is
owned by the CoLAB platform organization (see
`models.organization.OrganizationType.PLATFORM`), not a NULL/magic
tenant. Visibility for customer tenants is a read-side rule implemented
in `services/intelligence_service.py` (published + an
`IntelligenceDistribution` grant), never a change to Layer 1's
`authorize()` — see that service's module docstring for the full
reasoning.
"""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Enum, ForeignKey, String, Text, Date, DateTime, Boolean, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import AuditFieldsMixin, TimestampMixin, UUIDPKMixin


class IntelligenceScope(str, enum.Enum):
    GLOBAL = "GLOBAL"  # CoLAB-owned, distributed to authorized tenants
    TENANT = "TENANT"  # owned by a customer org, visible tenant-wide
    PRIVATE = "PRIVATE"  # owned by a customer org, visible to the creator (+ INTELLIGENCE_ADMINISTER) only


class IntelligenceType(str, enum.Enum):
    REGULATORY_GUIDELINE = "REGULATORY_GUIDELINE"
    REGULATORY_CHANGE = "REGULATORY_CHANGE"
    AGENCY_NEWS = "AGENCY_NEWS"
    INDUSTRY_NEWS = "INDUSTRY_NEWS"
    TENDER_ALERT = "TENDER_ALERT"
    PATENT_CLIFF = "PATENT_CLIFF"
    PARA_IV_CHALLENGE = "PARA_IV_CHALLENGE"
    PHARMA_EVENT = "PHARMA_EVENT"
    SAFETY_COMPLIANCE_ALERT = "SAFETY_COMPLIANCE_ALERT"


class IntelligenceStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    UNDER_REVIEW = "UNDER_REVIEW"
    PUBLISHED = "PUBLISHED"
    WITHDRAWN = "WITHDRAWN"
    ARCHIVED = "ARCHIVED"


# Controlled transitions (spec §9), same pattern as Layer 2's
# ALLOWED_DOSSIER_TRANSITIONS — an edge not listed here is a 409
# regardless of permission, enforced in intelligence_service.
ALLOWED_INTELLIGENCE_TRANSITIONS: dict[IntelligenceStatus, set[IntelligenceStatus]] = {
    IntelligenceStatus.DRAFT: {IntelligenceStatus.UNDER_REVIEW, IntelligenceStatus.ARCHIVED},
    IntelligenceStatus.UNDER_REVIEW: {IntelligenceStatus.DRAFT, IntelligenceStatus.PUBLISHED, IntelligenceStatus.ARCHIVED},
    IntelligenceStatus.PUBLISHED: {IntelligenceStatus.WITHDRAWN, IntelligenceStatus.ARCHIVED},
    IntelligenceStatus.WITHDRAWN: {IntelligenceStatus.UNDER_REVIEW, IntelligenceStatus.ARCHIVED},
    IntelligenceStatus.ARCHIVED: set(),
}


class ImpactLevel(str, enum.Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFORMATIONAL = "INFORMATIONAL"


class SourceType(str, enum.Enum):
    REGULATORY_AUTHORITY = "REGULATORY_AUTHORITY"
    INDUSTRY_PUBLICATION = "INDUSTRY_PUBLICATION"
    NEWS_AGGREGATOR = "NEWS_AGGREGATOR"
    OTHER = "OTHER"


class CollectionMethod(str, enum.Enum):
    """Foundation only — no method here is actually implemented in Layer
    3 (spec explicitly excludes crawler infrastructure); this just
    records how a source *would* be collected once Layer 6 builds it."""

    MANUAL = "MANUAL"
    RSS = "RSS"
    API = "API"
    SCRAPE = "SCRAPE"


class IntelligenceSource(UUIDPKMixin, TimestampMixin, Base):
    """Configurable registry (spec §4) — no website list hard-coded into
    application logic. Global reference data, same treatment as
    RegulatoryAuthority: not tenant-owned, seeded/managed centrally."""

    __tablename__ = "intelligence_sources"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType, name="intelligence_source_type"), nullable=False)
    authority_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("regulatory_authorities.id", ondelete="SET NULL"), nullable=True
    )
    country_region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", nullable=False)
    collection_method: Mapped[CollectionMethod] = mapped_column(
        Enum(CollectionMethod, name="intelligence_collection_method"), default=CollectionMethod.MANUAL, nullable=False
    )
    frequency: Mapped[str | None] = mapped_column(String(64), nullable=True)  # freeform: "DAILY", "WEEKLY", ...
    reliability_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_successful_collection_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attempted_collection_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    configuration_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON-encoded


class RegulatoryIntelligenceItem(UUIDPKMixin, TimestampMixin, AuditFieldsMixin, Base):
    __tablename__ = "regulatory_intelligence_items"

    # Owning org — CoLAB's platform org for GLOBAL items, a customer org
    # for TENANT/PRIVATE items. Always real (spec confirmation: no NULL
    # tenant-zero special case).
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    scope: Mapped[IntelligenceScope] = mapped_column(Enum(IntelligenceScope, name="intelligence_scope"), nullable=False, index=True)

    source_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("intelligence_sources.id", ondelete="SET NULL"), nullable=True
    )
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    # Deliberately a *reference*, not a blob of scraped HTML/text (spec
    # §2: "Do not store scraped content blindly") — a URL, a document_id
    # (Layer 1 Document) encoded as text, or a citation string.
    full_content_reference: Mapped[str | None] = mapped_column(Text, nullable=True)

    intelligence_type: Mapped[IntelligenceType] = mapped_column(
        Enum(IntelligenceType, name="intelligence_type"), nullable=False, index=True
    )
    authority_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("regulatory_authorities.id", ondelete="SET NULL"), nullable=True
    )
    country_region: Mapped[str | None] = mapped_column(String(64), nullable=True)

    publication_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_review_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    status: Mapped[IntelligenceStatus] = mapped_column(
        Enum(IntelligenceStatus, name="intelligence_status"), default=IntelligenceStatus.DRAFT, nullable=False, index=True
    )

    impact_level: Mapped[ImpactLevel] = mapped_column(Enum(ImpactLevel, name="impact_level"), nullable=False)
    # spec §8: "store the reason/source for an impact assessment" and
    # "must not assume AI is always responsible" — both fields required,
    # `assessed_by` nullable only because a system/seed action has no
    # human actor.
    impact_reason: Mapped[str] = mapped_column(Text, nullable=False)
    impact_assessed_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    impact_assessment_source: Mapped[str] = mapped_column(String(32), default="MANUAL", nullable=False)  # MANUAL | AI_ASSISTED

    therapeutic_area: Mapped[str | None] = mapped_column(String(255), nullable=True)
    regulatory_area: Mapped[str | None] = mapped_column(String(255), nullable=True)


class IntelligenceTag(UUIDPKMixin, Base):
    """Configurable tags (spec §10) — not hundreds of hard-coded values;
    an admin-managed, growable vocabulary."""

    __tablename__ = "intelligence_tags"
    __table_args__ = (UniqueConstraint("tag_type", "name", name="uq_intelligence_tag_type_name"),)

    tag_type: Mapped[str] = mapped_column(String(32), nullable=False)  # AUTHORITY, COUNTRY, REGION, THERAPEUTIC_AREA, ...
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class IntelligenceItemTag(Base):
    __tablename__ = "intelligence_item_tags"

    intelligence_item_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("regulatory_intelligence_items.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("intelligence_tags.id", ondelete="CASCADE"), primary_key=True
    )


class IntelligenceDistribution(UUIDPKMixin, Base):
    """The explicit authorization gate for GLOBAL intelligence (spec §5:
    "potentially distributed to multiple authorized tenants"; §24 test
    5: "distributed only according to configured authorization"). A
    customer org sees a GLOBAL+PUBLISHED item if and only if a row here
    grants it to them — there is no implicit "all customers see all
    global items" default.
    """

    __tablename__ = "intelligence_distributions"
    __table_args__ = (UniqueConstraint("intelligence_item_id", "organization_id", name="uq_intelligence_distribution"),)

    intelligence_item_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("regulatory_intelligence_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    distributed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    distributed_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)


class IntelligenceObjectLink(UUIDPKMixin, Base):
    """Prepares links to Layer 2 regulatory objects (spec §14) without
    building any automatic dossier modification. `linked_object_id` is
    unconstrained (varies by type) — same pattern as `Scope.resource_id`
    in Layer 1. Tenant-owned object types (PRODUCT, REGULATORY_PORTFOLIO,
    APPLICATION, DOSSIER, REGULATORY_ACTIVITY) may only be linked from an
    intelligence item in that SAME organization — enforced in
    intelligence_service, not at the schema level, exactly like
    Layer 2's own cross-entity checks."""

    __tablename__ = "intelligence_object_links"

    intelligence_item_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("regulatory_intelligence_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    linked_object_type: Mapped[str] = mapped_column(String(32), nullable=False)  # PRODUCT, DOSSIER, CTD_MODULE, ...
    linked_object_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
