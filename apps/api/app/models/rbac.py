"""
RBAC + Scope + SoD foundation (spec §15-23, §29).

Deliberately NOT `User -> Role`. The chain is:

    User -> Organization -> Role -> Permission -> Scope -> Resource
         -> Resource State -> Workflow/SoD Policy -> Authorization Decision -> Audit

`UserRoleAssignment` is the join that carries a Role *at* a Scope for a
User; `authorize()` (see services/authorization_service.py) is the one
place all of this gets evaluated.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, String, Boolean, DateTime, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPKMixin


class PermissionAction(str, enum.Enum):
    VIEW = "VIEW"
    CREATE = "CREATE"
    EDIT = "EDIT"
    DELETE = "DELETE"
    REVIEW = "REVIEW"
    APPROVE = "APPROVE"
    EXPORT = "EXPORT"
    PUBLISH = "PUBLISH"
    ADMINISTER = "ADMINISTER"


class PermissionDomain(str, enum.Enum):
    """Namespaces (spec §18). Extensible — Layer 1 seeds a representative
    subset, not every future domain."""

    DOCUMENT = "DOCUMENT"
    SUBMISSION = "SUBMISSION"
    RESPONSE = "RESPONSE"
    INTELLIGENCE = "INTELLIGENCE"
    AUDIT = "AUDIT"
    USER = "USER"
    ROLE = "ROLE"
    ORGANIZATION = "ORGANIZATION"
    ACCESS = "ACCESS"
    STANDARDS = "STANDARDS"
    # --- Layer 2 additions (Dossier & CTD Foundation) ---
    PRODUCT = "PRODUCT"
    AUTHORITY = "AUTHORITY"
    APPLICATION = "APPLICATION"
    DOSSIER = "DOSSIER"
    ACTIVITY = "ACTIVITY"
    # --- Layer 3 additions (Regulatory Intelligence Foundation) ---
    # NOTE: INTELLIGENCE itself already existed above (Layer 1 §18
    # anticipated this domain) — only the two new sub-domains are added
    # here; Layer 3 is what actually builds INTELLIGENCE_VIEW etc. for
    # real.
    INTELLIGENCE_SOURCE = "INTELLIGENCE_SOURCE"
    INTELLIGENCE_CONFIGURATION = "INTELLIGENCE_CONFIGURATION"


class RoleCategory(str, enum.Enum):
    PLATFORM = "PLATFORM"  # CoLAB Super Admin, System Administrator, ...
    REGULATORY_TEMPLATE = "REGULATORY_TEMPLATE"  # RA Trainee, Senior RA Specialist, ...
    CUSTOM = "CUSTOM"  # org-defined, cloned from a template


class ScopeType(str, enum.Enum):
    ORGANIZATION = "ORGANIZATION"
    BUSINESS_UNIT = "BUSINESS_UNIT"
    PRODUCT = "PRODUCT"
    MARKET = "MARKET"
    APPLICATION = "APPLICATION"
    REGISTRATION = "REGISTRATION"
    SUBMISSION = "SUBMISSION"
    SEQUENCE = "SEQUENCE"
    DOCUMENT = "DOCUMENT"


class ResourceState(str, enum.Enum):
    """Generic lifecycle state (spec §21). Individual resource types
    (Document, etc.) reuse this rather than each defining their own,
    so the "EDIT does not imply editing an APPROVED record" policy is
    written once in the authorization engine."""

    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    EFFECTIVE = "EFFECTIVE"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"


class Permission(UUIDPKMixin, Base):
    __tablename__ = "permissions"
    __table_args__ = (UniqueConstraint("domain", "action", name="uq_permissions_domain_action"),)

    domain: Mapped[PermissionDomain] = mapped_column(Enum(PermissionDomain, name="permission_domain"), nullable=False)
    action: Mapped[PermissionAction] = mapped_column(Enum(PermissionAction, name="permission_action"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)  # e.g. "DOCUMENT_VIEW"
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Role(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_roles_org_code"),)

    # NULL organization_id = platform-level role (CoLAB Super Admin, etc.)
    # or a template row that is copied, not referenced, when an org adopts it.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[RoleCategory] = mapped_column(Enum(RoleCategory, name="role_category"), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system_role: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )  # platform roles (§16); cannot be edited/deleted via API


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )


class Scope(UUIDPKMixin, Base):
    """A node in the generic scope hierarchy (spec §19). Layer 1 does not
    yet have real Product/Market/Application tables (those are Regulatory
    Master Data — a Layer 2 concern), so `resource_id` is an
    unconstrained UUID reference: it points at a future table's row once
    that table exists, and at nothing (label-only) until then.
    """

    __tablename__ = "scopes"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scope_type: Mapped[ScopeType] = mapped_column(Enum(ScopeType, name="scope_type"), nullable=False)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("scopes.id", ondelete="CASCADE"), nullable=True
    )
    label: Mapped[str] = mapped_column(String(255), nullable=False)  # e.g. "Product ABC / India"


class UserRoleAssignment(UUIDPKMixin, Base):
    """A Role granted to a User, optionally bounded to a Scope
    (NULL scope_id = the whole organization) and optionally time-bounded
    (spec §22 — external consultants)."""

    __tablename__ = "user_role_assignments"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    scope_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("scopes.id", ondelete="CASCADE"), nullable=True
    )
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    granted_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SoDPolicy(UUIDPKMixin, Base):
    """Segregation-of-duties rule (spec §20): the same user may not hold
    both `action_a` and `action_b` on the same resource. Layer 1 ships
    the data model and `authorize()` reads it, but does not yet enforce
    every possible future workflow policy.
    """

    __tablename__ = "sod_policies"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    action_a: Mapped[PermissionAction] = mapped_column(Enum(PermissionAction, name="sod_action_a"), nullable=False)
    action_b: Mapped[PermissionAction] = mapped_column(Enum(PermissionAction, name="sod_action_b"), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ElectronicSignatureStatus(str, enum.Enum):
    VALID = "VALID"
    REVOKED = "REVOKED"


class ElectronicSignature(UUIDPKMixin, Base):
    """Data model + interface only (spec §29) — no regulatory signing
    workflow is implemented in Layer 1."""

    __tablename__ = "electronic_signatures"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    signer_user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    role_at_signing: Mapped[str] = mapped_column(String(255), nullable=False)
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    meaning: Mapped[str] = mapped_column(String(255), nullable=False)  # e.g. "Approved for submission"
    authentication_context: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. "password", "mfa"
    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    object_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[ElectronicSignatureStatus] = mapped_column(
        Enum(ElectronicSignatureStatus, name="esignature_status"),
        default=ElectronicSignatureStatus.VALID,
        nullable=False,
    )
