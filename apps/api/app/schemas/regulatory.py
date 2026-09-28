import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.models.regulatory_activity import RegulatoryActivityType
from app.models.regulatory_structure import DevelopmentStatus, ProductStatus, RegulatoryApplicationType


class ProductCreateRequest(BaseModel):
    name: str
    business_unit_id: uuid.UUID | None = None
    product_family: str | None = None
    active_ingredient: str | None = None
    dosage_form: str | None = None
    strength: str | None = None
    route_of_administration: str | None = None
    indication: str | None = None
    development_status: DevelopmentStatus = DevelopmentStatus.CLINICAL_DEVELOPMENT
    status: ProductStatus = ProductStatus.ACTIVE


class ProductResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    product_family: str | None
    active_ingredient: str | None
    dosage_form: str | None
    strength: str | None
    route_of_administration: str | None
    indication: str | None
    development_status: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AuthorityResponse(BaseModel):
    id: uuid.UUID
    name: str
    short_name: str
    country: str | None
    region: str
    authority_type: str
    status: str

    model_config = {"from_attributes": True}


class RegulatoryApplicationCreateRequest(BaseModel):
    product_id: uuid.UUID
    authority_id: uuid.UUID
    country_region: str
    application_type: RegulatoryApplicationType
    application_number: str | None = None


class RegulatoryApplicationResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    product_id: uuid.UUID
    authority_id: uuid.UUID
    country_region: str
    application_type: str
    application_number: str | None
    regulatory_status: str | None
    lifecycle_status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DossierCreateRequest(BaseModel):
    product_id: uuid.UUID
    regulatory_application_id: uuid.UUID
    authority_id: uuid.UUID
    region: str
    ctd_standard: str = "eCTD"
    standard_version: str


class DossierResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    product_id: uuid.UUID
    regulatory_application_id: uuid.UUID
    authority_id: uuid.UUID
    region: str
    ctd_standard: str
    standard_version: str
    status: str
    owner_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DossierTransitionRequest(BaseModel):
    new_status: str
    reason: str | None = None


class CTDModuleResponse(BaseModel):
    id: uuid.UUID
    code: str
    title: str
    display_order: int
    authority_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class CTDSectionResponse(BaseModel):
    id: uuid.UUID
    module_id: uuid.UUID
    parent_section_id: uuid.UUID | None
    section_code: str
    title: str
    region: str | None
    authority_id: uuid.UUID | None
    display_order: int
    active: bool

    model_config = {"from_attributes": True}


class DocumentPlacementRequest(BaseModel):
    document_id: uuid.UUID
    ctd_section_id: uuid.UUID
    regulatory_activity_id: uuid.UUID | None = None


class DocumentPlacementResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    dossier_id: uuid.UUID
    ctd_section_id: uuid.UUID
    regulatory_activity_id: uuid.UUID | None
    placed_at: datetime

    model_config = {"from_attributes": True}


class RegulatoryActivityCreateRequest(BaseModel):
    product_id: uuid.UUID
    authority_id: uuid.UUID
    activity_type: RegulatoryActivityType
    regulatory_application_id: uuid.UUID | None = None
    dossier_id: uuid.UUID | None = None
    planned_date: date | None = None
    owner_id: uuid.UUID | None = None


class RegulatoryActivityResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    product_id: uuid.UUID
    regulatory_application_id: uuid.UUID | None
    dossier_id: uuid.UUID | None
    authority_id: uuid.UUID
    activity_type: str
    status: str
    planned_date: date | None
    actual_date: date | None

    model_config = {"from_attributes": True}


class RegulatoryEventResponse(BaseModel):
    id: uuid.UUID
    event_type: str
    dossier_id: uuid.UUID | None
    regulatory_activity_id: uuid.UUID | None
    document_id: uuid.UUID | None
    actor_user_id: uuid.UUID | None
    occurred_at: datetime
    description: str | None

    model_config = {"from_attributes": True}
