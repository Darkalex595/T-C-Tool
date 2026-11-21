from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

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


async def list_audit_logs(
    db: AsyncSession,
    *,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[UserAuditLog], int]:
    """Consulta paginada del registro inmutable de auditoría con filtros flexibles."""
    filters = []
    if action and action.strip():
        filters.append(UserAuditLog.action.ilike(f"%{action.strip()}%"))
    if entity_type and entity_type.strip():
        filters.append(UserAuditLog.entity_type == entity_type.strip().lower())
    if entity_id and entity_id.strip():
        filters.append(UserAuditLog.entity_id == entity_id.strip())
    if actor_user_id is not None:
        filters.append(UserAuditLog.actor_user_id == actor_user_id)

    total = int(
        await db.scalar(select(func.count(UserAuditLog.id)).where(*filters)) or 0
    )
    stmt = (
        select(UserAuditLog)
        .options(joinedload(UserAuditLog.actor_user))
        .where(*filters)
        .order_by(UserAuditLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = list((await db.scalars(stmt)).unique().all())
    return items, total
