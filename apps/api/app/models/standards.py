"""
Regulatory standards registry — foundation only (spec §32-33).

This is metadata about standards, not the standards' rules. Layer 1
explicitly must NOT hard-code ICH/FDA/EU rule content into business
logic — later layers read the actual rule sets from the source
documents this registry points at (spec §68: SOURCE -> VERSION ->
RULESET -> IMPLEMENTATION -> TEST -> EVIDENCE).
"""
import enum
import uuid
from datetime import date

from sqlalchemy import Enum, String, Date, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPKMixin


class DocumentStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    FINAL = "FINAL"
    SUPERSEDED = "SUPERSEDED"
    RETIRED = "RETIRED"


class RegulatoryStandard(UUIDPKMixin, TimestampMixin, Base):
    """e.g. "ICH eCTD v4.0", "FDA eCTD Validation Criteria"."""

    __tablename__ = "regulatory_standards"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    authority: Mapped[str] = mapped_column(String(128), nullable=False)  # ICH, FDA, EMA, ...
    region: Mapped[str] = mapped_column(String(64), nullable=False)  # GLOBAL, US, EU, ...
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class StandardVersion(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "standard_versions"

    standard_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("regulatory_standards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_label: Mapped[str] = mapped_column(String(32), nullable=False)  # "2.2", "1.6", "9.3", ...
    document_status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="standard_document_status"), default=DocumentStatus.FINAL, nullable=False
    )
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    retirement_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_reference: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )  # citation / filename of the supplied source document


class RegionalImplementation(UUIDPKMixin, Base):
    """e.g. "EU eCTD Module 1 Implementation Guide" as the EU's
    implementation of the ICH eCTD standard."""

    __tablename__ = "regional_implementations"

    standard_version_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("standard_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    region: Mapped[str] = mapped_column(String(64), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
