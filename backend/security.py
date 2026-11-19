from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import get_async_db
from backend.models import User

# Hasher Argon2id recomendado por pwdlib (estándar moderno frente a bcrypt)
_password_hasher = PasswordHash.recommended()

# Esquema Bearer para Swagger (/docs) y clientes REST
bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(plain_password: str) -> str:
    """Genera un hash seguro Argon2id a partir de una contraseña en texto plano."""
    return _password_hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verifica una contraseña contra su hash Argon2id sin lanzar excepción si el hash es inválido."""
    try:
        return _password_hasher.verify(plain_password, password_hash)
    except UnknownHashError:
        return False


def create_access_token(
    user_id: uuid.UUID,
    role_name: str,
    expires_delta: timedelta | None = None,
) -> tuple[str, int]:
    """Firma un JWT de acceso con expiración y devuelve (token, expires_in_seconds)."""
    now = datetime.now(timezone.utc)
    delta = expires_delta or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    expire_at = now + delta

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role_name,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expire_at.timestamp()),
    }
    token = jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    return token, int(delta.total_seconds())


def decode_access_token(token: str) -> dict[str, Any]:
    """Decodifica y valida firma, expiración y tipo de un JWT de acceso."""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token de autenticación inválido o expirado.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except InvalidTokenError as exc:
        raise credentials_exc from exc

    if payload.get("type") != "access" or not payload.get("sub"):
        raise credentials_exc
    return payload


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_async_db),
) -> User:
    """Dependencia FastAPI: extrae el Bearer token, valida el JWT y carga el User activo."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere cabecera Authorization: Bearer <token>.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(credentials.credentials)
    try:
        user_id = uuid.UUID(str(payload["sub"]))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identificador de usuario inválido en el token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    stmt = select(User).where(User.id == user_id)
    user = await db.scalar(stmt)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El usuario asociado al token ya no existe.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La cuenta de usuario se encuentra desactivada.",
        )

    return user


def require_permissions(*required_codes: str) -> Callable[..., Any]:
    """
    Fábrica de dependencias RBAC.
    Ejemplo: Depends(require_permissions("requests:assess"))
    """

    async def _permission_checker(
        current_user: User = Depends(get_current_user),
    ) -> User:
        user_permissions = {perm.code for perm in current_user.role.permissions}
        missing = [code for code in required_codes if code not in user_permissions]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permisos insuficientes. Requiere: {', '.join(missing)}.",
            )
        return current_user

    return _permission_checker
