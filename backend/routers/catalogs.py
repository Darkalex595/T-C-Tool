from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_db
from backend.models import User
from backend.schemas.catalogs import (
    CategoryCreate,
    CategoryRead,
    CountryRead,
    DepartmentCreate,
    DepartmentRead,
    DepartmentTreeRead,
    FiscalYearRead,
    SubcategoryCreate,
    SubcategoryRead,
)
from backend.security import get_current_user, require_permissions
from backend.services import catalogs as catalog_service

router = APIRouter(prefix="/catalogs", tags=["Catalogs & Taxonomy"])


@router.get("/countries", response_model=list[CountryRead])
async def get_countries(
    active_only: bool = Query(default=True),
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> list[CountryRead]:
    """Lista los países disponibles en el catálogo maestro."""
    countries = await catalog_service.list_countries(db, active_only=active_only)
    return [CountryRead.model_validate(c) for c in countries]


@router.get("/fiscal-years", response_model=list[FiscalYearRead])
async def get_fiscal_years(
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> list[FiscalYearRead]:
    """Lista los años fiscales configurados."""
    years = await catalog_service.list_fiscal_years(db)
    return [FiscalYearRead.model_validate(fy) for fy in years]


@router.get("/taxonomy", response_model=list[DepartmentTreeRead])
async def get_taxonomy_tree(
    active_only: bool = Query(default=True),
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> list[DepartmentTreeRead]:
    """Devuelve el árbol jerárquico completo Department > Category > Subcategory."""
    tree = await catalog_service.get_taxonomy_tree(db, active_only=active_only)
    return [DepartmentTreeRead.model_validate(dept) for dept in tree]


@router.post(
    "/departments",
    response_model=DepartmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_department(
    payload: DepartmentCreate,
    request: Request,
    current_user: User = Depends(require_permissions("users:admin")),
    db: AsyncSession = Depends(get_async_db),
) -> DepartmentRead:
    dept = await catalog_service.create_department(
        db,
        payload,
        actor=current_user,
        ip_address=request.client.host if request.client else None,
    )
    return DepartmentRead.model_validate(dept)


@router.post(
    "/categories",
    response_model=CategoryRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_category(
    payload: CategoryCreate,
    request: Request,
    current_user: User = Depends(require_permissions("users:admin")),
    db: AsyncSession = Depends(get_async_db),
) -> CategoryRead:
    category = await catalog_service.create_category(
        db,
        payload,
        actor=current_user,
        ip_address=request.client.host if request.client else None,
    )
    return CategoryRead.model_validate(category)


@router.post(
    "/subcategories",
    response_model=SubcategoryRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_subcategory(
    payload: SubcategoryCreate,
    request: Request,
    current_user: User = Depends(require_permissions("users:admin")),
    db: AsyncSession = Depends(get_async_db),
) -> SubcategoryRead:
    subcategory = await catalog_service.create_subcategory(
        db,
        payload,
        actor=current_user,
        ip_address=request.client.host if request.client else None,
    )
    return SubcategoryRead.model_validate(subcategory)
