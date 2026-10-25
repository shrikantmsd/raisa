"""
User — enterprise user management (spec §12).

Statuses are INVITED / ACTIVE / SUSPENDED / DEACTIVATED, never a hard
delete: "Do NOT permanently delete regulated historical user identities
simply because access is revoked." Soft-delete is available via
SoftDeleteMixin for the rare case a record must be archived outright,
but day-to-day offboarding should move status to DEACTIVATED instead.
"""
import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, Boolean, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from app.core.database import Base
from app.models.base import AuditFieldsMixin, SoftDeleteMixin, TimestampMixin, UUIDPKMixin
from app.models.organization import ThemeName


class UserStatus(str, enum.Enum):
    INVITED = "INVITED"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DEACTIVATED = "DEACTIVATED"


class MFAStatus(str, enum.Enum):
    DISABLED = "DISABLED"
    ENABLED = "ENABLED"


class User(UUIDPKMixin, TimestampMixin, AuditFieldsMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("organization_id", "email", name="uq_users_org_email"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(255), nullable=True)

    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status"), default=UserStatus.INVITED, nullable=False
    )

    time_zone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    locale: Mapped[str] = mapped_column(String(16), default="en-US", nullable=False)
    theme_preference: Mapped[ThemeName] = mapped_column(
        Enum(ThemeName, name="user_theme_preference"), default=ThemeName.SYSTEM, nullable=False
    )

    mfa_status: Mapped[MFAStatus] = mapped_column(
        Enum(MFAStatus, name="mfa_status"), default=MFAStatus.DISABLED, nullable=False
    )

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # External Consultant / CRO foundation (spec §22): NULL for
    # ordinary employees; when set, the authorization engine treats
    # `valid_until` in the past as an automatic DENY regardless of
    # any role/permission grant.
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.email!r} ({self.status.value})>"
