"""
Shared model foundation (spec §9 — Database Foundation).

Every domain model composes these mixins rather than redefining its
own id/timestamp/audit columns, so the convention is enforced in one
place instead of copy-pasted per table.

Note on internal identifiers (spec §9): the UUIDs generated here are
RAISA's own internal entity identifiers. They are NOT eCTD UUID/OID
values and must never be reused as such — later layers that deal with
eCTD sequences mint their own regulatory identifiers, kept in
dedicated columns, never aliased to `id`.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UUIDPKMixin:
    """Internal RAISA identifier. See module docstring."""

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class AuditFieldsMixin:
    """`created_by` / `updated_by` are intentionally plain UUID columns,
    not enforced foreign keys. Several foundation tables (Organization,
    User) would otherwise need a circular FK to `users.id` before the
    first user can exist. Referential integrity for these fields is a
    later-layer concern once a bootstrap/system-actor convention is
    defined; for now they are populated by the service layer from the
    authenticated actor (or left NULL for system/seed-initiated writes).
    """

    created_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)


class SoftDeleteMixin:
    """Records are archived, not destroyed, by default (spec §12 —
    "Do NOT permanently delete regulated historical ... identities").
    `deleted_at IS NULL` means live; services should filter on it
    explicitly since Layer 1 does not install a global ORM event that
    would silently rewrite every query.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


def tenant_fk(nullable: bool = False):
    """Every tenant-owned table gets an `organization_id` column via
    this helper, so the FK target/ondelete policy is defined once
    (spec §10 — every tenant-owned record must have tenant_id).
    """
    return mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=nullable,
        index=True,
    )
