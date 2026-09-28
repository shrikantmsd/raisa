import uuid

from pydantic import BaseModel


class RoleResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    category: str
    description: str | None

    model_config = {"from_attributes": True}


class PermissionResponse(BaseModel):
    id: uuid.UUID
    code: str
    domain: str
    action: str
    description: str | None

    model_config = {"from_attributes": True}


class AccessPreviewRequest(BaseModel):
    domain: str
    action: str
    scope_id: uuid.UUID | None = None


class AccessPreviewResponse(BaseModel):
    allowed: bool
    reason: str
    policy: str | None = None
    role_id: uuid.UUID | None = None
    permission_code: str | None = None
