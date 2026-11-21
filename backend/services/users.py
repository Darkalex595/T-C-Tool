from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import Country, Permission, Role, User
from backend.schemas.auth import (
    AdminResetPasswordRequest,
    ChangePasswordRequest,
    CreateUserRequest,
    RoleCreate,
    RoleUpdate,
    UpdateUserRequest,
    UserProfileResponse,
)
from backend.security import hash_password, verify_password
from backend.services.audit import record_audit_log


def serialize_user_profile(user: User) -> UserProfileResponse:
    """Convierte un ORM User (con Role y Permissions cargados) a su DTO seguro."""
    return UserProfileResponse(
        id=str(user.id),
        full_name=user.full_name,
        email=user.email,
        role=user.role.name,
        permissions=sorted(perm.code for perm in user.role.permissions),
        primary_country_code=user.primary_country_code,
        department_code=user.department_code,
        is_active=user.is_active,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
    )


async def _ensure_country_exists(db: AsyncSession, country_code: str) -> str:
    code = country_code.strip().upper()
    exists = await db.scalar(select(Country.code).where(Country.code == code))
    if exists is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Código de país '{code}' no encontrado.",
        )
    return code


async def _get_role_by_name(db: AsyncSession, role_name: str) -> Role:
    normalized = role_name.strip().lower()
    role = await db.scalar(
        select(Role).options(selectinload(Role.permissions)).where(Role.name == normalized)
    )
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El rol '{role_name}' no existe.",
        )
    return role


# =============================================================================
# GESTIÓN DE USUARIOS Y CONTRASEÑAS
# =============================================================================


async def list_users(
    db: AsyncSession,
    *,
    search: str | None = None,
    role_name: str | None = None,
    country_code: str | None = None,
    is_active: bool | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[User], int]:
    filters = []
    if is_active is not None:
        filters.append(User.is_active.is_(is_active))
    if country_code:
        filters.append(User.primary_country_code == country_code.strip().upper())
    if role_name:
        filters.append(User.role.has(Role.name == role_name.strip().lower()))
    if search and search.strip():
        term = f"%{search.strip()}%"
        filters.append(
            or_(
                User.full_name.ilike(term),
                User.email.ilike(term),
                User.department_code.ilike(term),
            )
        )

    total = int(await db.scalar(select(func.count(User.id)).where(*filters)) or 0)
    stmt = (
        select(User)
        .where(*filters)
        .order_by(User.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    users = list((await db.scalars(stmt)).unique().all())
    return users, total


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado.",
        )
    return user


async def create_user(
    db: AsyncSession,
    payload: CreateUserRequest,
    actor: User,
    ip_address: str | None = None,
) -> User:
    normalized_email = payload.email.strip().lower()
    existing = await db.scalar(select(User.id).where(User.email == normalized_email))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe una cuenta registrada con el email '{normalized_email}'.",
        )

    role = await _get_role_by_name(db, payload.role_name)

    country_code: str | None = None
    if payload.primary_country_code:
        country_code = await _ensure_country_exists(db, payload.primary_country_code)

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

    record_audit_log(
        db,
        actor_user_id=actor.id,
        action="users.create",
        entity_type="user",
        entity_id=new_user.id,
        changes_payload={"email": normalized_email, "role": role.name},
        ip_address=ip_address,
    )
    return await get_user_by_id(db, new_user.id)


async def update_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    payload: UpdateUserRequest,
    actor: User,
    ip_address: str | None = None,
) -> User:
    user = await get_user_by_id(db, user_id)
    changes = payload.model_dump(exclude_unset=True)
    audit_changes: dict[str, object] = {}

    if "is_active" in changes and changes["is_active"] is False and user.id == actor.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes desactivar tu propia cuenta de administrador.",
        )

    if "role_name" in changes and changes["role_name"] is not None:
        new_role = await _get_role_by_name(db, changes["role_name"])
        new_perm_codes = {p.code for p in new_role.permissions}
        if user.id == actor.id and "users:admin" not in new_perm_codes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No puedes remover el permiso 'users:admin' de tu propia cuenta.",
            )
        audit_changes["role_from"] = user.role.name
        audit_changes["role_to"] = new_role.name
        user.role_id = new_role.id

    if "primary_country_code" in changes:
        country_val = changes["primary_country_code"]
        user.primary_country_code = (
            await _ensure_country_exists(db, country_val) if country_val else None
        )
        audit_changes["primary_country_code"] = user.primary_country_code

    if "full_name" in changes and changes["full_name"] is not None:
        user.full_name = changes["full_name"].strip()
        audit_changes["full_name"] = user.full_name

    if "department_code" in changes:
        user.department_code = changes["department_code"]
        audit_changes["department_code"] = user.department_code

    if "is_active" in changes and changes["is_active"] is not None:
        user.is_active = changes["is_active"]
        audit_changes["is_active"] = user.is_active

    await db.flush()
    record_audit_log(
        db,
        actor_user_id=actor.id,
        action="users.update",
        entity_type="user",
        entity_id=user.id,
        changes_payload=audit_changes,
        ip_address=ip_address,
    )
    # Recargar explícitamente para reflejar el nuevo rol/permisos en el objeto ORM
    await db.refresh(user, attribute_names=["role"])
    return await get_user_by_id(db, user.id)


async def change_own_password(
    db: AsyncSession,
    payload: ChangePasswordRequest,
    current_user: User,
    ip_address: str | None = None,
) -> None:
    """Permite al usuario autenticado cambiar su propia contraseña verificando la actual."""
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña actual es incorrecta.",
        )

    current_user.password_hash = hash_password(payload.new_password)
    await db.flush()

    record_audit_log(
        db,
        actor_user_id=current_user.id,
        action="auth.password_changed",
        entity_type="user",
        entity_id=current_user.id,
        changes_payload={"self_service": True},
        ip_address=ip_address,
    )


async def admin_reset_password(
    db: AsyncSession,
    user_id: uuid.UUID,
    payload: AdminResetPasswordRequest,
    actor: User,
    ip_address: str | None = None,
) -> User:
    """Permite a un administrador restablecer la contraseña de cualquier usuario."""
    user = await get_user_by_id(db, user_id)
    user.password_hash = hash_password(payload.new_password)
    await db.flush()

    record_audit_log(
        db,
        actor_user_id=actor.id,
        action="users.password_reset",
        entity_type="user",
        entity_id=user.id,
        changes_payload={"target_email": user.email},
        ip_address=ip_address,
    )
    return user


# =============================================================================
# GESTIÓN DE ROLES Y PERMISOS RBAC
# =============================================================================


async def list_permissions(db: AsyncSession) -> list[Permission]:
    stmt = select(Permission).order_by(Permission.module.asc(), Permission.action.asc())
    return list((await db.scalars(stmt)).all())


async def list_roles(db: AsyncSession) -> list[Role]:
    stmt = (
        select(Role)
        .options(selectinload(Role.permissions))
        .order_by(Role.is_system.desc(), Role.name.asc())
    )
    return list((await db.scalars(stmt)).all())


async def get_role_by_id(db: AsyncSession, role_id: uuid.UUID) -> Role:
    role = await db.scalar(
        select(Role).options(selectinload(Role.permissions)).where(Role.id == role_id)
    )
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rol no encontrado.",
        )
    return role


async def _load_permissions_by_codes(
    db: AsyncSession, codes: list[str]
) -> list[Permission]:
    if not codes:
        return []
    unique_codes = list(dict.fromkeys(c.strip().lower() for c in codes if c.strip()))
    perms = list(
        (await db.scalars(select(Permission).where(Permission.code.in_(unique_codes)))).all()
    )
    found_codes = {p.code for p in perms}
    missing = sorted(set(unique_codes) - found_codes)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Permisos no reconocidos: {', '.join(missing)}.",
        )
    return perms


async def create_role(
    db: AsyncSession,
    payload: RoleCreate,
    actor: User,
    ip_address: str | None = None,
) -> Role:
    existing = await db.scalar(select(Role.id).where(Role.name == payload.name))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un rol llamado '{payload.name}'.",
        )

    permissions = await _load_permissions_by_codes(db, payload.permission_codes)
    role = Role(
        name=payload.name,
        description=payload.description,
        is_system=False,
        permissions=permissions,
    )
    db.add(role)
    await db.flush()

    record_audit_log(
        db,
        actor_user_id=actor.id,
        action="roles.create",
        entity_type="role",
        entity_id=role.id,
        changes_payload={
            "name": role.name,
            "permissions": sorted(p.code for p in permissions),
        },
        ip_address=ip_address,
    )
    return await get_role_by_id(db, role.id)


async def update_role(
    db: AsyncSession,
    role_id: uuid.UUID,
    payload: RoleUpdate,
    actor: User,
    ip_address: str | None = None,
) -> Role:
    role = await get_role_by_id(db, role_id)
    changes = payload.model_dump(exclude_unset=True)
    audit_payload: dict[str, object] = {"role_name": role.name}

    if "description" in changes:
        role.description = changes["description"]
        audit_payload["description"] = role.description

    if "permission_codes" in changes and changes["permission_codes"] is not None:
        new_codes = changes["permission_codes"]
        if role.name == "admin" and "users:admin" not in new_codes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El rol de sistema 'admin' siempre debe conservar el permiso 'users:admin'.",
            )
        role.permissions = await _load_permissions_by_codes(db, new_codes)
        audit_payload["permissions"] = sorted(p.code for p in role.permissions)

    await db.flush()
    record_audit_log(
        db,
        actor_user_id=actor.id,
        action="roles.update",
        entity_type="role",
        entity_id=role.id,
        changes_payload=audit_payload,
        ip_address=ip_address,
    )
    return await get_role_by_id(db, role.id)


async def delete_role(
    db: AsyncSession,
    role_id: uuid.UUID,
    actor: User,
    ip_address: str | None = None,
) -> None:
    role = await get_role_by_id(db, role_id)
    if role.is_system:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No se puede eliminar el rol de sistema '{role.name}'.",
        )

    assigned_users_count = int(
        await db.scalar(select(func.count(User.id)).where(User.role_id == role.id)) or 0
    )
    if assigned_users_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"No se puede eliminar el rol '{role.name}' porque tiene "
                f"{assigned_users_count} usuario(s) asignado(s)."
            ),
        )

    role_name = role.name
    await db.delete(role)
    await db.flush()

    record_audit_log(
        db,
        actor_user_id=actor.id,
        action="roles.delete",
        entity_type="role",
        entity_id=role_id,
        changes_payload={"name": role_name},
        ip_address=ip_address,
    )
