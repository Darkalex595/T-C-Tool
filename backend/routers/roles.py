from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_db
from backend.models import User
from backend.schemas.auth import PermissionRead, RoleCreate, RoleRead, RoleUpdate
from backend.security import require_permissions
from backend.services import users as user_service

router = APIRouter(prefix="/roles", tags=["Roles & Permissions"])


@router.get("/permissions", response_model=list[PermissionRead])
async def list_permissions(
    _current_user: User = Depends(require_permissions("users:admin")),
    db: AsyncSession = Depends(get_async_db),
) -> list[PermissionRead]:
    """Lista el catálogo completo de permisos disponibles para asignar a roles."""
    perms = await user_service.list_permissions(db)
    return [PermissionRead.model_validate(p) for p in perms]


@router.get("", response_model=list[RoleRead])
async def list_roles(
    _current_user: User = Depends(require_permissions("users:admin")),
    db: AsyncSession = Depends(get_async_db),
) -> list[RoleRead]:
    """Lista todos los roles con sus permisos asignados."""
    roles = await user_service.list_roles(db)
    return [RoleRead.model_validate(r) for r in roles]


@router.get("/{role_id}", response_model=RoleRead)
async def get_role(
    role_id: UUID,
    _current_user: User = Depends(require_permissions("users:admin")),
    db: AsyncSession = Depends(get_async_db),
) -> RoleRead:
    role = await user_service.get_role_by_id(db, role_id)
    return RoleRead.model_validate(role)


@router.post("", response_model=RoleRead, status_code=status.HTTP_201_CREATED)
async def create_role(
    payload: RoleCreate,
    request: Request,
    current_user: User = Depends(require_permissions("users:admin")),
    db: AsyncSession = Depends(get_async_db),
) -> RoleRead:
    """Crea un rol personalizado asignando los códigos de permiso deseados."""
    role = await user_service.create_role(
        db,
        payload,
        actor=current_user,
        ip_address=request.client.host if request.client else None,
    )
    return RoleRead.model_validate(role)


@router.patch("/{role_id}", response_model=RoleRead)
async def update_role(
    role_id: UUID,
    payload: RoleUpdate,
    request: Request,
    current_user: User = Depends(require_permissions("users:admin")),
    db: AsyncSession = Depends(get_async_db),
) -> RoleRead:
    """Actualiza la descripción y/o los permisos efectivos de un rol."""
    role = await user_service.update_role(
        db,
        role_id,
        payload,
        actor=current_user,
        ip_address=request.client.host if request.client else None,
    )
    return RoleRead.model_validate(role)


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: UUID,
    request: Request,
    current_user: User = Depends(require_permissions("users:admin")),
    db: AsyncSession = Depends(get_async_db),
) -> Response:
    """Elimina un rol personalizado (bloquea roles de sistema o con usuarios activos)."""
    await user_service.delete_role(
        db,
        role_id,
        actor=current_user,
        ip_address=request.client.host if request.client else None,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
