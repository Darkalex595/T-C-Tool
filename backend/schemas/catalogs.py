from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.models import ProductClassification


class CountryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    region: str
    currency_code: str
    regulatory_agency: str | None
    is_active: bool


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
