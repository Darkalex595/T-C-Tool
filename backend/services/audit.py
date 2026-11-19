from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import UserAuditLog


def record_audit_log(
    db: AsyncSession,
    *,
    actor_user_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: str | uuid.UUID | None,
    changes_payload: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> UserAuditLog:
    """Agrega un evento inmutable de auditoría dentro de la transacción activa."""
    log_entry = UserAuditLog(
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        changes_payload=changes_payload,
        ip_address=ip_address,
    )
    db.add(log_entry)
    return log_entry
