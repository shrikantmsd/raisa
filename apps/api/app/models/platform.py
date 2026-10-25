"""
Configuration, feature flags, and notifications — foundation only
(spec §30-31, §52). Infrastructure for future modules; Layer 1 does not
activate any flagged module just because the flag row exists.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, String, Boolean, DateTime, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPKMixin


class ConfigurationScope(str, enum.Enum):
    PLATFORM = "PLATFORM"
    ORGANIZATION = "ORGANIZATION"


class Configuration(UUIDPKMixin, TimestampMixin, Base):
    """Generic key/value settings store. Business configuration lives
    here, never in frontend code (spec §30)."""

    __tablename__ = "configurations"
    __table_args__ = (UniqueConstraint("scope", "organization_id", "key", name="uq_configuration_scope_org_key"),)

    scope: Mapped[ConfigurationScope] = mapped_column(Enum(ConfigurationScope, name="configuration_scope"), nullable=False)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)  # JSON-encoded


class FeatureFlag(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "feature_flags"

    key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)  # e.g. "response_center"
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled_globally: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class FeatureFlagOverride(Base):
    """Per-organization override of a global flag."""

    __tablename__ = "feature_flag_overrides"

    feature_flag_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("feature_flags.id", ondelete="CASCADE"), primary_key=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)


class NotificationStatus(str, enum.Enum):
    UNREAD = "UNREAD"
    READ = "READ"
    DISMISSED = "DISMISSED"


class Notification(UUIDPKMixin, Base):
    __tablename__ = "notifications"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus, name="notification_status"), default=NotificationStatus.UNREAD, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    action_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
