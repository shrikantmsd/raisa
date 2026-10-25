"""
CTD structure as real data, not folders (Layer 2 spec §5). `CTDModule`
and `CTDSection` are the populated realization of the registry
*architecture* Layer 1 §34 already established (Layer 1 deliberately
left it empty) — this is that registry, not a second one.

`DocumentCTDPlacement` is the explicit Document -> CTD Location
relationship spec §12/§25 asks for as first-class data rather than an
inferred folder path, and is what a future Context of Use engine
(Layer 4) will read instead of every document only ever living in
exactly one place.
"""
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, Boolean, Integer, UniqueConstraint, DateTime
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import UUIDPKMixin


class CTDModule(UUIDPKMixin, Base):
    """Modules 1-5. Global reference data — the CTD structure itself
    doesn't vary by tenant (spec §5: "the application must know what a
    CTD module ... represents"), only which sections a given dossier
    actually uses does.
    """

    __tablename__ = "ctd_modules"

    code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)  # "MODULE_1".."MODULE_5"
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
    # Module 1 is authority/region-specific (spec §6) — NULL here means
    # "the universal module" (2-5); a non-NULL authority_id means this
    # row is one authority's specific take on Module 1.
    authority_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("regulatory_authorities.id", ondelete="CASCADE"), nullable=True
    )


class CTDSection(UUIDPKMixin, Base):
    __tablename__ = "ctd_sections"
    __table_args__ = (UniqueConstraint("module_id", "section_code", "authority_id", name="uq_ctd_section_identity"),)

    module_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("ctd_modules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_section_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("ctd_sections.id", ondelete="CASCADE"), nullable=True
    )
    section_code: Mapped[str] = mapped_column(String(32), nullable=False)  # "2.3", "3.2.S", "5.3.5.1"
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    standard_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("standard_versions.id", ondelete="SET NULL"), nullable=True
    )
    region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Denormalized off the module for authority-specific Module 1
    # sections, so a section can be queried without a module join.
    authority_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("regulatory_authorities.id", ondelete="CASCADE"), nullable=True
    )
    applicability: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class DocumentCTDPlacement(UUIDPKMixin, Base):
    """The Document <-> CTD Location relationship (spec §12, §25) as a
    join table rather than columns on `Document` itself: a document can
    in principle be placed in more than one location over its life
    (reuse across amendments is explicitly a future-layer Context-of-
    Use concept, spec Layer 1 §24) — modeling it as a join now means
    that future capability doesn't require restructuring this table,
    only relaxing a uniqueness constraint.
    """

    __tablename__ = "document_ctd_placements"
    __table_args__ = (UniqueConstraint("document_id", "dossier_id", "ctd_section_id", name="uq_document_placement"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dossier_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ctd_section_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("ctd_sections.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    regulatory_activity_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("regulatory_activities.id", ondelete="SET NULL"), nullable=True
    )
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    placed_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
