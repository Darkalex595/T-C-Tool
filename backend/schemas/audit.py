from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.schemas.auth import UserSummary


class AuditLogRead(BaseModel):
    """Registro inmutable de auditoría para trazabilidad administrativa."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    actor_user_id: UUID | None
    actor_user: UserSummary | None = None
    action: str
    entity_type: str
    entity_id: str | None
    changes_payload: dict[str, Any] | None
    ip_address: str | None
    created_at: datetime
