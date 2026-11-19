from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_db
from backend.models import Country, Role, User, UserAuditLog
from backend.schemas.auth import (
    CreateUserRequest,
    LoginRequest,
    LoginResponse,
    UserProfileResponse,
)
from backend.security import (
    create_access_token,
    get_current_user,
    hash_password,
    require_permissions,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["Auth & RBAC"])


def _serialize_user(user: User) -> UserProfileResponse:
    return UserProfileResponse(
        id=str(user.id),
        full_name=user.full_name,
        email=user.email,
        role=user.role.name,
        permissions=sorted(perm.code for perm in user.role.permissions),
        primary_country_code=user.primary_country_code,
        department_code=user.department_code,
        is_active=user.is_active,
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
) -> LoginResponse:
    """Autentica al usuario con email + contraseña Argon2id y emite un JWT Bearer."""
    normalized_email = payload.email.strip().lower()
    user = await db.scalar(select(User).where(User.email == normalized_email))

    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La cuenta de usuario está desactivada.",
        )

    user.last_login_at = datetime.now(timezone.utc)
    db.add(
        UserAuditLog(
            actor_user_id=user.id,
            action="auth.login",
            entity_type="user",
            entity_id=str(user.id),
            changes_payload={"role": user.role.name},
            ip_address=request.client.host if request.client else None,
        )
    )

    token, expires_in = create_access_token(user_id=user.id, role_name=user.role.name)
    return LoginResponse(
        access_token=token,
        expires_in=expires_in,
        user=_serialize_user(user),
    )


@router.get("/me", response_model=UserProfileResponse)
async def read_current_user(
    current_user: User = Depends(get_current_user),
) -> UserProfileResponse:
    """Devuelve el perfil, rol y permisos efectivos del usuario autenticado."""
    return _serialize_user(current_user)


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
    """Crea un nuevo usuario (solo accesible para roles con permiso `users:admin`)."""
    normalized_email = payload.email.strip().lower()
    existing = await db.scalar(select(User.id).where(User.email == normalized_email))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe una cuenta registrada con el email '{normalized_email}'.",
        )

    role = await db.scalar(select(Role).where(Role.name == payload.role_name.strip()))
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El rol '{payload.role_name}' no existe.",
        )

    country_code: str | None = None
    if payload.primary_country_code:
        country_code = payload.primary_country_code.strip().upper()
        country_exists = await db.scalar(
            select(Country.code).where(Country.code == country_code)
        )
        if country_exists is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Código de país '{country_code}' no encontrado.",
            )

    new_user = User(
        full_name=payload.full_name.strip(),
        email=normalized_email,
        password_hash=hash_password(payload.password),
        role_id=role.id,
        primary_country_code=country_code,
        department_code=payload.department_code,
    )
    db.add(new_user)
    await db.flush()

    db.add(
        UserAuditLog(
            actor_user_id=current_user.id,
            action="users.create",
            entity_type="user",
            entity_id=str(new_user.id),
            changes_payload={"email": normalized_email, "role": role.name},
            ip_address=request.client.host if request.client else None,
        )
    )

    loaded_user = await db.scalar(select(User).where(User.id == new_user.id))
    assert loaded_user is not None
    return _serialize_user(loaded_user)


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
