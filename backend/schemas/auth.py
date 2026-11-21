from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class UserSummary(BaseModel):
    """Vista resumida de usuario para embeber en solicitudes, dictámenes o logs."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    email: str


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=150)
    password: str = Field(..., min_length=1, max_length=128)


class ChangePasswordRequest(BaseModel):
    """Cambio de contraseña del propio usuario autenticado."""

    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)

    @model_validator(mode="after")
    def ensure_different_password(self) -> ChangePasswordRequest:
        if self.current_password == self.new_password:
            raise ValueError("La nueva contraseña debe ser diferente a la actual.")
        return self


class AdminResetPasswordRequest(BaseModel):
    """Restablecimiento de contraseña ejecutado por un administrador."""

    new_password: str = Field(..., min_length=8, max_length=128)


class CreateUserRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=120)
    email: str = Field(..., min_length=5, max_length=150)
    password: str = Field(..., min_length=8, max_length=128)
    role_name: str = Field(default="buyer", max_length=60)
    primary_country_code: str | None = Field(default=None, min_length=2, max_length=2)
    department_code: str | None = Field(default=None, max_length=40)

    @field_validator("primary_country_code")
    @classmethod
    def normalize_country(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None


class UpdateUserRequest(BaseModel):
    """Edición parcial de perfil, rol o estado activo de un usuario."""

    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    role_name: str | None = Field(default=None, min_length=2, max_length=60)
    primary_country_code: str | None = Field(default=None, min_length=2, max_length=2)
    department_code: str | None = Field(default=None, max_length=40)
    is_active: bool | None = None

    @field_validator("primary_country_code")
    @classmethod
    def normalize_country(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None


class UserProfileResponse(BaseModel):
    id: str
    full_name: str
    email: str
    role: str
    permissions: list[str]
    primary_country_code: str | None
    department_code: str | None
    is_active: bool
    last_login_at: datetime | None = None
    created_at: datetime | None = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserProfileResponse


# --- Roles y Permisos RBAC ---


class PermissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    module: str
    action: str
    code: str
    description: str | None


class RoleCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=60)
    description: str | None = Field(default=None, max_length=255)
    permission_codes: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip().lower().replace(" ", "_")

    @field_validator("permission_codes")
    @classmethod
    def normalize_codes(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(v.strip().lower() for v in values if v.strip()))


class RoleUpdate(BaseModel):
    description: str | None = Field(default=None, max_length=255)
    permission_codes: list[str] | None = None

    @field_validator("permission_codes")
    @classmethod
    def normalize_codes(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        return list(dict.fromkeys(v.strip().lower() for v in values if v.strip()))


class RoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    is_system: bool
    permissions: list[PermissionRead] = Field(default_factory=list)
    created_at: datetime
