from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UserSummary(BaseModel):
    """Vista resumida de usuario para embeber en solicitudes, dictámenes o logs."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    email: str


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=150)
    password: str = Field(..., min_length=1, max_length=128)


class CreateUserRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=120)
    email: str = Field(..., min_length=5, max_length=150)
    password: str = Field(..., min_length=8, max_length=128)
    role_name: str = Field(default="buyer", max_length=60)
    primary_country_code: str | None = Field(default=None, min_length=2, max_length=2)
    department_code: str | None = Field(default=None, max_length=40)


class UserProfileResponse(BaseModel):
    id: str
    full_name: str
    email: str
    role: str
    permissions: list[str]
    primary_country_code: str | None
    department_code: str | None
    is_active: bool


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserProfileResponse
