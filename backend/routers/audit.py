from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_db
from backend.models import User
from backend.schemas.audit import AuditLogRead
from backend.schemas.requests import PaginatedResponse
from backend.security import require_permissions
from backend.services import audit as audit_service

router = APIRouter(prefix="/audit-logs", tags=["Audit Logs"])


@router.get("", response_model=PaginatedResponse[AuditLogRead])
async def list_audit_logs(
    action: str | None = Query(default=None, max_length=80),
    entity_type: str | None = Query(default=None, max_length=60),
    entity_id: str | None = Query(default=None, max_length=64),
    actor_user_id: UUID | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _current_user: User = Depends(require_permissions("users:admin")),
    db: AsyncSession = Depends(get_async_db),
) -> PaginatedResponse[AuditLogRead]:
    """Consulta paginada de la bitácora inmutable de auditoría (solo `users:admin`)."""
    items, total = await audit_service.list_audit_logs(
        db,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse(
        items=[AuditLogRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )
