from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import User
from backend.schemas.auth import LoginRequest, LoginResponse
from backend.security import create_access_token, verify_password
from backend.services import users as user_service
from backend.services.audit import record_audit_log


async def authenticate_user(
    db: AsyncSession,
    payload: LoginRequest,
    ip_address: str | None = None,
) -> LoginResponse:
    """
    Valida credenciales (email + hash Argon2id), verifica que la cuenta esté activa,
    actualiza `last_login_at`, registra la auditoría y emite el token JWT Bearer.
    """
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
    await db.flush()

    record_audit_log(
        db,
        actor_user_id=user.id,
        action="auth.login",
        entity_type="user",
        entity_id=user.id,
        changes_payload={"role": user.role.name},
        ip_address=ip_address,
    )

    token, expires_in = create_access_token(user_id=user.id, role_name=user.role.name)
    return LoginResponse(
        access_token=token,
        expires_in=expires_in,
        user=user_service.serialize_user_profile(user),
    )
