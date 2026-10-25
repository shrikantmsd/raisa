import uuid
from datetime import datetime

from pydantic import BaseModel


class AuditEventResponse(BaseModel):
    id: uuid.UUID
    event_type: str
    object_type: str
    object_id: uuid.UUID | None
    user_id: uuid.UUID | None
    occurred_at: datetime
    reason: str | None
    source: str

    model_config = {"from_attributes": True}
