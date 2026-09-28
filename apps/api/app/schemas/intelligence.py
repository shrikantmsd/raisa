import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.models.intelligence import (
    CollectionMethod,
    ImpactLevel,
    IntelligenceScope,
    IntelligenceStatus,
    IntelligenceType,
    SourceType,
)


class IntelligenceItemCreateRequest(BaseModel):
    scope: IntelligenceScope
    intelligence_type: IntelligenceType
    title: str
    summary: str
    full_content_reference: str | None = None
    source_id: uuid.UUID | None = None
    source_url: str | None = None
    authority_id: uuid.UUID | None = None
    country_region: str | None = None
    publication_date: date | None = None
    effective_date: date | None = None
    expiry_review_date: date | None = None
    impact_level: ImpactLevel
    impact_reason: str
    impact_assessment_source: str = "MANUAL"
    therapeutic_area: str | None = None
    regulatory_area: str | None = None


class IntelligenceItemUpdateRequest(BaseModel):
    """Every field optional; only what's sent is changed. `scope` is
    intentionally not here — it's fixed at creation — and extra fields are
    rejected (422) rather than silently ignored, so a client that tries
    to change scope finds out instead of assuming it worked."""

    model_config = {"extra": "forbid"}

    title: str | None = None
    summary: str | None = None
    full_content_reference: str | None = None
    source_id: uuid.UUID | None = None
    source_url: str | None = None
    authority_id: uuid.UUID | None = None
    country_region: str | None = None
    publication_date: date | None = None
    effective_date: date | None = None
    expiry_review_date: date | None = None
    intelligence_type: IntelligenceType | None = None
    impact_level: ImpactLevel | None = None
    impact_reason: str | None = None
    impact_assessment_source: str | None = None
    therapeutic_area: str | None = None
    regulatory_area: str | None = None


class IntelligenceItemResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    scope: str
    intelligence_type: str
    title: str
    summary: str
    full_content_reference: str | None
    source_id: uuid.UUID | None
    source_url: str | None
    authority_id: uuid.UUID | None
    country_region: str | None
    publication_date: date | None
    effective_date: date | None
    expiry_review_date: date | None
    status: str
    impact_level: str
    impact_reason: str
    therapeutic_area: str | None
    regulatory_area: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class IntelligenceTransitionRequest(BaseModel):
    new_status: IntelligenceStatus
    reason: str | None = None


class DistributionRequest(BaseModel):
    target_organization_id: uuid.UUID


class SourceCreateRequest(BaseModel):
    name: str
    source_type: SourceType
    authority_id: uuid.UUID | None = None
    country_region: str | None = None
    url: str | None = None
    frequency: str | None = None


class SourceUpdateRequest(BaseModel):
    model_config = {"extra": "forbid"}

    name: str | None = None
    source_type: SourceType | None = None
    authority_id: uuid.UUID | None = None
    country_region: str | None = None
    url: str | None = None
    status: str | None = None
    collection_method: CollectionMethod | None = None
    frequency: str | None = None
    reliability_notes: str | None = None
    active: bool | None = None


class SuggestedOrganization(BaseModel):
    id: uuid.UUID
    name: str
    slug: str

    model_config = {"from_attributes": True}


class SourceResponse(BaseModel):
    id: uuid.UUID
    name: str
    source_type: str
    authority_id: uuid.UUID | None
    country_region: str | None
    url: str | None
    status: str
    active: bool

    model_config = {"from_attributes": True}


class TagResponse(BaseModel):
    id: uuid.UUID
    tag_type: str
    name: str
    active: bool

    model_config = {"from_attributes": True}


class TagCreateRequest(BaseModel):
    tag_type: str
    name: str


class ObjectLinkRequest(BaseModel):
    linked_object_type: str
    linked_object_id: uuid.UUID


class TenantPreferencesRequest(BaseModel):
    countries: list[str] = []
    authorities: list[str] = []
    therapeutic_areas: list[str] = []
    intelligence_types: list[str] = []
