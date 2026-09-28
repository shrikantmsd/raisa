"""
Layer 2 — Product/Portfolio + Regulatory Authority + Application
foundation (Layer 2 spec §1-3).

`RegulatoryAuthority` is deliberately GLOBAL reference data (no
organization_id) — FDA is FDA regardless of which tenant references it,
the same way Layer 1's `Permission` table is shared reference data
rather than per-tenant. Everything else here is tenant-owned.
"""
import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import AuditFieldsMixin, TimestampMixin, UUIDPKMixin


class DevelopmentStatus(str, enum.Enum):
    PRECLINICAL = "PRECLINICAL"
    CLINICAL_DEVELOPMENT = "CLINICAL_DEVELOPMENT"
    MARKETED = "MARKETED"
    DISCONTINUED = "DISCONTINUED"


class ProductStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    DISCONTINUED = "DISCONTINUED"


class Product(UUIDPKMixin, TimestampMixin, AuditFieldsMixin, Base):
    """Tenant §1: "A product must never be globally visible across
    tenants unless explicitly represented as approved global reference
    data" — Layer 2 implements no such global product yet, so every
    Product row is strictly tenant-owned."""

    __tablename__ = "products"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    business_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("business_units.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_family: Mapped[str | None] = mapped_column(String(255), nullable=True)
    active_ingredient: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dosage_form: Mapped[str | None] = mapped_column(String(128), nullable=True)
    strength: Mapped[str | None] = mapped_column(String(128), nullable=True)
    route_of_administration: Mapped[str | None] = mapped_column(String(128), nullable=True)
    indication: Mapped[str | None] = mapped_column(Text, nullable=True)
    development_status: Mapped[DevelopmentStatus] = mapped_column(
        Enum(DevelopmentStatus, name="development_status"), default=DevelopmentStatus.CLINICAL_DEVELOPMENT, nullable=False
    )
    status: Mapped[ProductStatus] = mapped_column(
        Enum(ProductStatus, name="product_status"), default=ProductStatus.ACTIVE, nullable=False
    )


class RegulatoryPortfolio(UUIDPKMixin, TimestampMixin, AuditFieldsMixin, Base):
    """Groups a product's regulatory work (spec §1's Product -> Portfolio
    -> Application -> Dossier chain). Deliberately thin in Layer 2 — a
    name/description grouping, not yet a planning tool."""

    __tablename__ = "regulatory_portfolios"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class AuthorityType(str, enum.Enum):
    NATIONAL = "NATIONAL"
    REGIONAL = "REGIONAL"
    OTHER = "OTHER"


class RegulatoryAuthority(UUIDPKMixin, TimestampMixin, Base):
    """Global reference data (spec §2) — seeded, not tenant-created.
    "Supported regulatory standards/submission types/eCTD versions" are
    deliberately NOT columns here: that's exactly the Layer 1 Ruleset
    Registry's job (spec Layer 2 §2: "Authority-specific behavior must
    eventually be driven by the Ruleset Registry established in Layer
    1"), so this stays identity + metadata only.
    """

    __tablename__ = "regulatory_authorities"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    short_name: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)  # "FDA", "EMA", "CDSCO"
    country: Mapped[str | None] = mapped_column(String(128), nullable=True)
    region: Mapped[str] = mapped_column(String(64), nullable=False)  # US, EU, IN, GLOBAL, ...
    authority_type: Mapped[AuthorityType] = mapped_column(Enum(AuthorityType, name="authority_type"), nullable=False)
    status: Mapped[ProductStatus] = mapped_column(  # reuse ACTIVE/INACTIVE vocabulary, no need for a 3rd enum
        Enum(ProductStatus, name="authority_status"), default=ProductStatus.ACTIVE, nullable=False
    )
    website_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    configuration_reference: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # pointer into the Layer 1 Ruleset Registry once populated


class RegulatoryApplicationType(str, enum.Enum):
    MARKETING_AUTHORIZATION = "MARKETING_AUTHORIZATION"
    VARIATION = "VARIATION"
    SUPPLEMENT = "SUPPLEMENT"
    RENEWAL = "RENEWAL"
    CLINICAL_TRIAL = "CLINICAL_TRIAL"
    OTHER = "OTHER"


class RegulatoryApplication(UUIDPKMixin, TimestampMixin, AuditFieldsMixin, Base):
    __tablename__ = "regulatory_applications"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    authority_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("regulatory_authorities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    country_region: Mapped[str] = mapped_column(String(64), nullable=False)
    application_type: Mapped[RegulatoryApplicationType] = mapped_column(
        Enum(RegulatoryApplicationType, name="regulatory_application_type"), nullable=False
    )
    application_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    regulatory_status: Mapped[str | None] = mapped_column(String(128), nullable=True)  # authority-facing status text
    lifecycle_status: Mapped[ProductStatus] = mapped_column(
        Enum(ProductStatus, name="application_lifecycle_status"), default=ProductStatus.ACTIVE, nullable=False
    )
