"""
Organization / BusinessUnit — the tenancy root (spec §10, §11).

`Organization` is the tenant boundary. Every tenant-owned table carries
an `organization_id` (see `models.base.tenant_fk`), and the
authorization engine resolves `organization_id` from the authenticated
session only — never from a client-supplied field.
"""
import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, Boolean, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import AuditFieldsMixin, TimestampMixin, UUIDPKMixin


class OrganizationStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    ARCHIVED = "ARCHIVED"


class OrganizationType(str, enum.Enum):
    """Layer 3 addition. PLATFORM identifies CoLAB Systems itself — the
    real, ordinary tenant that owns global intelligence — as opposed to
    a magic tenant-zero id (spec Layer 3 §1/§5-6). There should be
    exactly one PLATFORM row; nothing enforces that at the DB level in
    Layer 3 (no CHECK/partial-unique-index), it's a seed-time
    invariant — see docs/LAYER_3_REGULATORY_INTELLIGENCE.md."""

    PLATFORM = "PLATFORM"
    CUSTOMER = "CUSTOMER"


class ThemeName(str, enum.Enum):
    RAISA_OFFICE = "RAISA_OFFICE"
    RAISA_GENX = "RAISA_GENX"
    SYSTEM = "SYSTEM"


class Organization(UUIDPKMixin, TimestampMixin, AuditFieldsMixin, Base):
    __tablename__ = "organizations"
    __table_args__ = (UniqueConstraint("slug", name="uq_organizations_slug"),)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Login-facing tenant identifier (e.g. "acme-pharma"). Not part of the
    # spec's explicit field list, but something has to resolve "which
    # tenant" *before* credentials are checked (spec §13 login foundation) —
    # a slug is the simplest option that doesn't leak the internal UUID.
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[OrganizationStatus] = mapped_column(
        Enum(OrganizationStatus, name="organization_status"),
        default=OrganizationStatus.ACTIVE,
        nullable=False,
    )
    organization_type: Mapped[OrganizationType] = mapped_column(
        Enum(OrganizationType, name="organization_type"), default=OrganizationType.CUSTOMER, nullable=False
    )
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    default_locale: Mapped[str] = mapped_column(String(16), default="en-US", nullable=False)
    default_theme: Mapped[ThemeName] = mapped_column(
        Enum(ThemeName, name="theme_name"), default=ThemeName.RAISA_OFFICE, nullable=False
    )
    allow_user_theme_override: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Organization {self.name!r} ({self.id})>"


class BusinessUnit(UUIDPKMixin, TimestampMixin, AuditFieldsMixin, Base):
    __tablename__ = "business_units"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[OrganizationStatus] = mapped_column(
        Enum(OrganizationStatus, name="business_unit_status"),
        default=OrganizationStatus.ACTIVE,
        nullable=False,
    )
