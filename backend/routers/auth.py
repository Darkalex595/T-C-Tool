from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_db
from backend.models import User
from backend.schemas.auth import (
    ChangePasswordRequest,
    CreateUserRequest,
    LoginRequest,
    LoginResponse,
    UserProfileResponse,
)
from backend.security import get_current_user, require_permissions
from backend.services import auth as auth_service
from backend.services import users as user_service

router = APIRouter(prefix="/auth", tags=["Auth & RBAC"])


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
) -> LoginResponse:
    """Autentica al usuario con email + contraseña Argon2id y emite un JWT Bearer."""
    return await auth_service.authenticate_user(
        db,
        payload,
        ip_address=request.client.host if request.client else None,
    )


@router.get("/me", response_model=UserProfileResponse)
async def read_current_user(
    current_user: User = Depends(get_current_user),
) -> UserProfileResponse:
    """Devuelve el perfil, rol y permisos efectivos del usuario autenticado."""
    return user_service.serialize_user_profile(current_user)


@router.post("/change-password")
async def change_own_password(
    payload: ChangePasswordRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> dict[str, str]:
    """Permite al usuario autenticado actualizar su propia contraseña."""
    await user_service.change_own_password(
        db,
        payload,
        current_user=current_user,
        ip_address=request.client.host if request.client else None,
    )
    return {"detail": "Contraseña actualizada correctamente."}


@router.post(
    "/users",
    response_model=UserProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_user_as_admin(
    payload: CreateUserRequest,
    request: Request,
    current_user: User = Depends(require_permissions("users:admin")),
    db: AsyncSession = Depends(get_async_db),
) -> UserProfileResponse:
    """Alias compatible para crear un usuario (también disponible en POST /api/v1/users)."""
    new_user = await user_service.create_user(
        db,
        payload,
        actor=current_user,
        ip_address=request.client.host if request.client else None,
    )
    return user_service.serialize_user_profile(new_user)


@router.get("/rbac-check")
async def test_rbac_permission(
    current_user: User = Depends(require_permissions("requests:assess")),
) -> dict[str, object]:
    """Endpoint de verificación RBAC: solo accesible si el rol posee `requests:assess`."""
    return {
        "authorized": True,
        "user": current_user.email,
        "role": current_user.role.name,
        "required_permission": "requests:assess",
    }
