import uuid

from pydantic import BaseModel


class OrganizationResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    status: str
    timezone: str
    default_locale: str
    default_theme: str
    allow_user_theme_override: bool

    model_config = {"from_attributes": True}
