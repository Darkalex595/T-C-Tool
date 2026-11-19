from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.models import (
    LogisticsRouteCode,
    OriginScope,
    ProductClassification,
    RegulationStatus,
)
from backend.schemas.catalogs import SubcategoryRead


# --- Rutas Logísticas (ImportRoute) ---


class ImportRouteCreate(BaseModel):
    route_code: LogisticsRouteCode
    route_name: str = Field(..., min_length=3, max_length=120)
    dc_code: str = Field(..., min_length=2, max_length=30)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    classification: ProductClassification | None = None
    required_document: str = Field(..., min_length=3, max_length=200)
    description: str | None = None
    us_origin_rules: str | None = None
    non_us_origin_rules: str | None = None
    is_direct_to_destination: bool = False
    is_active: bool = True

    @field_validator("country_code")
    @classmethod
    def normalize_country_code(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None


class ImportRouteUpdate(BaseModel):
    route_name: str | None = Field(default=None, min_length=3, max_length=120)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    classification: ProductClassification | None = None
    required_document: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = None
    us_origin_rules: str | None = None
    non_us_origin_rules: str | None = None
    is_direct_to_destination: bool | None = None
    is_active: bool | None = None

    @field_validator("country_code")
    @classmethod
    def normalize_country_code(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None


class ImportRouteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    route_code: LogisticsRouteCode
    route_name: str
    dc_code: str
    country_code: str | None
    classification: ProductClassification | None
    required_document: str
    description: str | None
    us_origin_rules: str | None
    non_us_origin_rules: str | None
    is_direct_to_destination: bool
    is_active: bool


# --- Regulaciones Multinacionales (Regulation) ---


class RegulationCreate(BaseModel):
    country_code: str = Field(..., min_length=2, max_length=2)
    department_id: UUID | None = None
    regulation_code: str = Field(..., min_length=2, max_length=80)
    title: str = Field(..., min_length=4, max_length=220)
    issuing_authority: str = Field(..., min_length=2, max_length=160)
    status: RegulationStatus = RegulationStatus.ENFORCED
    summary: str = Field(..., min_length=10)
    requirements_detail: str | None = None
    effective_date: date | None = None
    expiration_date: date | None = None
    source_url: str | None = Field(default=None, max_length=500)
    metadata_extra: dict[str, Any] | None = None
    subcategory_ids: list[UUID] = Field(default_factory=list)

    @field_validator("country_code")
    @classmethod
    def normalize_country_code(cls, value: str) -> str:
        return value.strip().upper()


class RegulationUpdate(BaseModel):
    department_id: UUID | None = None
    title: str | None = Field(default=None, min_length=4, max_length=220)
    issuing_authority: str | None = Field(default=None, min_length=2, max_length=160)
    status: RegulationStatus | None = None
    summary: str | None = Field(default=None, min_length=10)
    requirements_detail: str | None = None
    effective_date: date | None = None
    expiration_date: date | None = None
    source_url: str | None = Field(default=None, max_length=500)
    metadata_extra: dict[str, Any] | None = None
    subcategory_ids: list[UUID] | None = None


class RegulationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    country_code: str
    department_id: UUID | None
    regulation_code: str
    title: str
    issuing_authority: str
    status: RegulationStatus
    summary: str
    requirements_detail: str | None
    effective_date: date | None
    expiration_date: date | None
    source_url: str | None
    metadata_extra: dict[str, Any] | None
    subcategories: list[SubcategoryRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


# --- Certificaciones Requeridas por Ítem (CertificationRequirement) ---


class CertificationCreate(BaseModel):
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    origin_scope: OriginScope = OriginScope.ALL
    certificate_name: str = Field(..., min_length=2, max_length=160)
    issuing_body: str | None = Field(default=None, max_length=160)
    is_mandatory: bool = True
    requires_apostille: bool = False
    validity_days: int | None = Field(default=None, gt=0)
    notes: str | None = None

    @field_validator("country_code")
    @classmethod
    def normalize_country_code(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None


class CertificationUpdate(BaseModel):
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    origin_scope: OriginScope | None = None
    certificate_name: str | None = Field(default=None, min_length=2, max_length=160)
    issuing_body: str | None = Field(default=None, max_length=160)
    is_mandatory: bool | None = None
    requires_apostille: bool | None = None
    validity_days: int | None = Field(default=None, gt=0)
    notes: str | None = None

    @field_validator("country_code")
    @classmethod
    def normalize_country_code(cls, value: str | None) -> str | None:
        return value.strip().upper() if value else None


class CertificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    req_general_id: UUID
    country_code: str | None
    origin_scope: OriginScope
    certificate_name: str
    issuing_body: str | None
    is_mandatory: bool
    requires_apostille: bool
    validity_days: int | None
    notes: str | None
