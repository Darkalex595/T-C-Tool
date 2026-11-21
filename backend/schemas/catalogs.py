from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.models import ProductClassification


# --- Países (Country) ---


class CountryCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=2)
    name: str = Field(..., min_length=2, max_length=100)
    region: str = Field(..., min_length=2, max_length=50)
    currency_code: str = Field(default="USD", min_length=3, max_length=3)
    regulatory_agency: str | None = Field(default=None, max_length=120)
    is_active: bool = True

    @field_validator("code", "currency_code", mode="before")
    @classmethod
    def normalize_upper(cls, value: str) -> str:
        return value.strip().upper() if isinstance(value, str) else value


class CountryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    region: str | None = Field(default=None, min_length=2, max_length=50)
    currency_code: str | None = Field(default=None, min_length=3, max_length=3)
    regulatory_agency: str | None = Field(default=None, max_length=120)
    is_active: bool | None = None

    @field_validator("currency_code", mode="before")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return value.strip().upper() if isinstance(value, str) else value


class CountryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    region: str
    currency_code: str
    regulatory_agency: str | None
    is_active: bool


# --- Años Fiscales (FiscalYear) ---


class FiscalYearCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=12)
    start_date: date
    end_date: date
    is_current: bool = False

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_date_range(self) -> FiscalYearCreate:
        if self.end_date <= self.start_date:
            raise ValueError("end_date debe ser estrictamente posterior a start_date.")
        return self


class FiscalYearUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=2, max_length=12)
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool | None = None

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: str | None) -> str | None:
        return value.strip().upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_date_range(self) -> FiscalYearUpdate:
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.end_date <= self.start_date
        ):
            raise ValueError("end_date debe ser estrictamente posterior a start_date.")
        return self


class FiscalYearRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    start_date: date
    end_date: date
    is_current: bool


# --- Jerarquía Comercial: Department > Category > Subcategory ---


class DepartmentCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=20)
    name: str = Field(..., min_length=2, max_length=120)
    is_active: bool = True


class DepartmentUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=2, max_length=20)
    name: str | None = Field(default=None, min_length=2, max_length=120)
    is_active: bool | None = None


class DepartmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    is_active: bool


class CategoryCreate(BaseModel):
    department_id: UUID
    code: str = Field(..., min_length=2, max_length=30)
    name: str = Field(..., min_length=2, max_length=120)
    classification: ProductClassification
    is_active: bool = True


class CategoryUpdate(BaseModel):
    department_id: UUID | None = None
    code: str | None = Field(default=None, min_length=2, max_length=30)
    name: str | None = Field(default=None, min_length=2, max_length=120)
    classification: ProductClassification | None = None
    is_active: bool | None = None


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    department_id: UUID
    code: str
    name: str
    classification: ProductClassification
    is_active: bool


class SubcategoryCreate(BaseModel):
    category_id: UUID
    code: str = Field(..., min_length=2, max_length=30)
    name: str = Field(..., min_length=2, max_length=140)
    hs_chapter_hint: str | None = Field(default=None, max_length=10)
    requires_sanitary_reg: bool = False
    is_active: bool = True


class SubcategoryUpdate(BaseModel):
    category_id: UUID | None = None
    code: str | None = Field(default=None, min_length=2, max_length=30)
    name: str | None = Field(default=None, min_length=2, max_length=140)
    hs_chapter_hint: str | None = Field(default=None, max_length=10)
    requires_sanitary_reg: bool | None = None
    is_active: bool | None = None


class SubcategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    category_id: UUID
    code: str
    name: str
    hs_chapter_hint: str | None
    requires_sanitary_reg: bool
    is_active: bool


class CategoryWithSubcategoriesRead(CategoryRead):
    """Categoría con sus subcategorías hijas para vistas en árbol."""

    subcategories: list[SubcategoryRead] = Field(default_factory=list)


class DepartmentTreeRead(DepartmentRead):
    """Árbol completo Department > Category > Subcategory."""

    categories: list[CategoryWithSubcategoriesRead] = Field(default_factory=list)
