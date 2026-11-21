from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_db
from backend.models import User
from backend.schemas.catalogs import (
    CategoryCreate,
    CategoryRead,
    CategoryUpdate,
    CountryCreate,
    CountryRead,
    CountryUpdate,
    DepartmentCreate,
    DepartmentRead,
    DepartmentTreeRead,
    DepartmentUpdate,
    FiscalYearCreate,
    FiscalYearRead,
    FiscalYearUpdate,
    SubcategoryCreate,
    SubcategoryRead,
    SubcategoryUpdate,
)
from backend.security import get_current_user, require_permissions
from backend.services import catalogs as catalog_service

router = APIRouter(prefix="/catalogs", tags=["Catalogs & Taxonomy"])


# --- Países ---


@router.get("/countries", response_model=list[CountryRead])
async def get_countries(
    active_only: bool = Query(default=True),
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> list[CountryRead]:
    """Lista los países disponibles en el catálogo maestro."""
    countries = await catalog_service.list_countries(db, active_only=active_only)
    return [CountryRead.model_validate(c) for c in countries]


@router.get("/countries/{country_code}", response_model=CountryRead)
async def get_country(
    country_code: str,
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> CountryRead:
    """Devuelve el detalle de un país por su código ISO-2."""
    country = await catalog_service.get_country_by_code(db, country_code)
    return CountryRead.model_validate(country)


@router.post(
    "/countries",
    response_model=CountryRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_country(
    payload: CountryCreate,
    request: Request,
    current_user: User = Depends(require_permissions("users:admin")),
    db: AsyncSession = Depends(get_async_db),
) -> CountryRead:
    """Registra un nuevo país (código ISO-2) en el catálogo maestro."""
    country = await catalog_service.create_country(
        db,
        payload,
        actor=current_user,
        ip_address=request.client.host if request.client else None,
    )
    return CountryRead.model_validate(country)


@router.patch("/countries/{country_code}", response_model=CountryRead)
async def update_country(
    country_code: str,
    payload: CountryUpdate,
    request: Request,
    current_user: User = Depends(require_permissions("users:admin")),
    db: AsyncSession = Depends(get_async_db),
) -> CountryRead:
    """Actualiza datos o estado activo de un país existente."""
    country = await catalog_service.update_country(
        db,
        country_code,
        payload,
        actor=current_user,
        ip_address=request.client.host if request.client else None,
    )
    return CountryRead.model_validate(country)


# --- Años Fiscales ---


@router.get("/fiscal-years", response_model=list[FiscalYearRead])
async def get_fiscal_years(
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> list[FiscalYearRead]:
    """Lista los años fiscales configurados."""
    years = await catalog_service.list_fiscal_years(db)
    return [FiscalYearRead.model_validate(fy) for fy in years]


@router.get("/fiscal-years/current", response_model=FiscalYearRead)
async def get_current_fiscal_year(
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> FiscalYearRead:
    """Devuelve el año fiscal vigente (`is_current=True`)."""
    fy = await catalog_service.get_current_fiscal_year(db)
    return FiscalYearRead.model_validate(fy)


@router.post(
    "/fiscal-years",
    response_model=FiscalYearRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_fiscal_year(
    payload: FiscalYearCreate,
    request: Request,
    current_user: User = Depends(require_permissions("users:admin")),
    db: AsyncSession = Depends(get_async_db),
) -> FiscalYearRead:
    """Crea un nuevo año fiscal (si is_current=True, desactiva los anteriores)."""
    fy = await catalog_service.create_fiscal_year(
        db,
        payload,
        actor=current_user,
        ip_address=request.client.host if request.client else None,
    )
    return FiscalYearRead.model_validate(fy)


@router.patch("/fiscal-years/{fiscal_year_id}", response_model=FiscalYearRead)
async def update_fiscal_year(
    fiscal_year_id: UUID,
    payload: FiscalYearUpdate,
    request: Request,
    current_user: User = Depends(require_permissions("users:admin")),
    db: AsyncSession = Depends(get_async_db),
) -> FiscalYearRead:
    """Actualiza fechas, código o vigencia actual de un año fiscal."""
    fy = await catalog_service.update_fiscal_year(
        db,
        fiscal_year_id,
        payload,
        actor=current_user,
        ip_address=request.client.host if request.client else None,
    )
    return FiscalYearRead.model_validate(fy)


# --- Taxonomía Comercial (Department > Category > Subcategory) ---


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


@router.patch("/departments/{department_id}", response_model=DepartmentRead)
async def update_department(
    department_id: UUID,
    payload: DepartmentUpdate,
    request: Request,
    current_user: User = Depends(require_permissions("users:admin")),
    db: AsyncSession = Depends(get_async_db),
) -> DepartmentRead:
    dept = await catalog_service.update_department(
        db,
        department_id,
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


@router.patch("/categories/{category_id}", response_model=CategoryRead)
async def update_category(
    category_id: UUID,
    payload: CategoryUpdate,
    request: Request,
    current_user: User = Depends(require_permissions("users:admin")),
    db: AsyncSession = Depends(get_async_db),
) -> CategoryRead:
    category = await catalog_service.update_category(
        db,
        category_id,
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


@router.patch("/subcategories/{subcategory_id}", response_model=SubcategoryRead)
async def update_subcategory(
    subcategory_id: UUID,
    payload: SubcategoryUpdate,
    request: Request,
    current_user: User = Depends(require_permissions("users:admin")),
    db: AsyncSession = Depends(get_async_db),
) -> SubcategoryRead:
    subcategory = await catalog_service.update_subcategory(
        db,
        subcategory_id,
        payload,
        actor=current_user,
        ip_address=request.client.host if request.client else None,
    )
    return SubcategoryRead.model_validate(subcategory)
