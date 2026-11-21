from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_db
from backend.models import User
from backend.schemas.auth import (
    AdminResetPasswordRequest,
    CreateUserRequest,
    UpdateUserRequest,
    UserProfileResponse,
)
from backend.schemas.requests import PaginatedResponse
from backend.security import require_permissions
from backend.services import users as user_service

router = APIRouter(prefix="/users", tags=["Users Management"])


@router.get("", response_model=PaginatedResponse[UserProfileResponse])
async def list_users(
    search: str | None = Query(default=None, max_length=120),
    role_name: str | None = Query(default=None, max_length=60),
    country_code: str | None = Query(default=None, min_length=2, max_length=2),
    is_active: bool | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _current_user: User = Depends(require_permissions("users:admin")),
    db: AsyncSession = Depends(get_async_db),
) -> PaginatedResponse[UserProfileResponse]:
    """Lista usuarios paginados con filtros por texto, rol, país o estado activo."""
    users, total = await user_service.list_users(
        db,
        search=search,
        role_name=role_name,
        country_code=country_code,
        is_active=is_active,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse(
        items=[user_service.serialize_user_profile(u) for u in users],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{user_id}", response_model=UserProfileResponse)
async def get_user(
    user_id: UUID,
    _current_user: User = Depends(require_permissions("users:admin")),
    db: AsyncSession = Depends(get_async_db),
) -> UserProfileResponse:
    user = await user_service.get_user_by_id(db, user_id)
    return user_service.serialize_user_profile(user)


@router.post(
    "",
    response_model=UserProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_user(
    payload: CreateUserRequest,
    request: Request,
    current_user: User = Depends(require_permissions("users:admin")),
    db: AsyncSession = Depends(get_async_db),
) -> UserProfileResponse:
    """Crea una nueva cuenta de usuario con hash Argon2id y rol asignado."""
    user = await user_service.create_user(
        db,
        payload,
        actor=current_user,
        ip_address=request.client.host if request.client else None,
    )
    return user_service.serialize_user_profile(user)


@router.patch("/{user_id}", response_model=UserProfileResponse)
async def update_user(
    user_id: UUID,
    payload: UpdateUserRequest,
    request: Request,
    current_user: User = Depends(require_permissions("users:admin")),
    db: AsyncSession = Depends(get_async_db),
) -> UserProfileResponse:
    """Edita nombre, rol, país, departamento o activa/desactiva una cuenta."""
    user = await user_service.update_user(
        db,
        user_id,
        payload,
        actor=current_user,
        ip_address=request.client.host if request.client else None,
    )
    return user_service.serialize_user_profile(user)


@router.post("/{user_id}/reset-password")
async def reset_user_password(
    user_id: UUID,
    payload: AdminResetPasswordRequest,
    request: Request,
    current_user: User = Depends(require_permissions("users:admin")),
    db: AsyncSession = Depends(get_async_db),
) -> dict[str, str]:
    """Permite al administrador restablecer la contraseña de cualquier usuario."""
    user = await user_service.admin_reset_password(
        db,
        user_id,
        payload,
        actor=current_user,
        ip_address=request.client.host if request.client else None,
    )
    return {"detail": f"Contraseña restablecida correctamente para '{user.email}'."}
