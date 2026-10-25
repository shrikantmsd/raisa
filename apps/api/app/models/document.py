"""
Document storage foundation (spec §24-26). Layer 1 scope only: metadata,
versioning, and a checksum — not CTD placement, eCTD lifecycle, Context
of Use, or XML serialization (those are later layers, spec §24).
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Enum, ForeignKey, String, DateTime, BigInteger
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import AuditFieldsMixin, TimestampMixin, UUIDPKMixin
from app.models.rbac import ResourceState


class ChecksumAlgorithm(str, enum.Enum):
    SHA256 = "SHA256"


class Document(UUIDPKMixin, TimestampMixin, AuditFieldsMixin, Base):
    __tablename__ = "documents"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    # Layer 2 addition: what the document IS in regulatory terms (e.g.
    # "Clinical Study Report", "Certificate of Analysis") — intrinsic to
    # the document, unlike *where* it sits (see DocumentCTDPlacement in
    # models/ctd.py, which is about placement, not identity).
    document_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[ResourceState] = mapped_column(
        Enum(ResourceState, name="document_status"), default=ResourceState.DRAFT, nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class DocumentVersion(UUIDPKMixin, Base):
    __tablename__ = "document_versions"

    document_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(nullable=False)
    # Tenant-aware object-storage path (spec §25) — never a raw public
    # bucket URL. The object-storage abstraction (services layer, later
    # layer) is the only thing allowed to turn this into a signed URL.
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_algorithm: Mapped[ChecksumAlgorithm] = mapped_column(
        Enum(ChecksumAlgorithm, name="checksum_algorithm"), default=ChecksumAlgorithm.SHA256, nullable=False
    )
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
