import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserCreateRequest(BaseModel):
    email: EmailStr
    name: str
    password: str
    department: str | None = None
    job_title: str | None = None


class UserResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    email: str
    name: str
    display_name: str | None
    department: str | None
    job_title: str | None
    status: str
    time_zone: str
    locale: str
    theme_preference: str
    mfa_status: str
    last_login_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
