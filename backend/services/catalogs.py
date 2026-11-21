from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import Category, Country, Department, FiscalYear, Subcategory, User
from backend.schemas.catalogs import (
    CategoryCreate,
    CategoryUpdate,
    CountryCreate,
    CountryUpdate,
    DepartmentCreate,
    DepartmentUpdate,
    FiscalYearCreate,
    FiscalYearUpdate,
    SubcategoryCreate,
    SubcategoryUpdate,
)
from backend.services.audit import record_audit_log


# =============================================================================
# PAÍSES (Country)
# =============================================================================


async def list_countries(db: AsyncSession, active_only: bool = True) -> list[Country]:
    """Lista el catálogo de países ordenados alfabéticamente."""
    stmt = select(Country).order_by(Country.name.asc())
    if active_only:
        stmt = stmt.where(Country.is_active.is_(True))
    result = await db.scalars(stmt)
    return list(result.all())


async def get_country_by_code(db: AsyncSession, country_code: str) -> Country:
    code = country_code.strip().upper()
    country = await db.scalar(select(Country).where(Country.code == code))
    if country is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"País '{code}' no encontrado.",
        )
    return country


async def create_country(
    db: AsyncSession,
    payload: CountryCreate,
    actor: User,
    ip_address: str | None = None,
) -> Country:
    """Registra un nuevo país (código ISO 3166-1 alpha-2) validando unicidad."""
    code = payload.code.strip().upper()
    name = payload.name.strip()

    duplicate = await db.scalar(
        select(Country.code).where((Country.code == code) | (Country.name == name))
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un país con código '{code}' o nombre '{name}'.",
        )

    country = Country(
        code=code,
        name=name,
        region=payload.region.strip(),
        currency_code=payload.currency_code.strip().upper(),
        regulatory_agency=payload.regulatory_agency,
        is_active=payload.is_active,
    )
    db.add(country)
    await db.flush()

    record_audit_log(
        db,
        actor_user_id=actor.id,
        action="catalogs.country_create",
        entity_type="country",
        entity_id=country.code,
        changes_payload={"code": country.code, "name": country.name, "region": country.region},
        ip_address=ip_address,
    )
    return country


async def update_country(
    db: AsyncSession,
    country_code: str,
    payload: CountryUpdate,
    actor: User,
    ip_address: str | None = None,
) -> Country:
    code = country_code.strip().upper()
    country = await db.scalar(select(Country).where(Country.code == code))
    if country is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"País '{code}' no encontrado.",
        )

    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] is not None:
        new_name = changes["name"].strip()
        duplicate = await db.scalar(
            select(Country.code).where(Country.name == new_name, Country.code != code)
        )
        if duplicate is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ya existe otro país con el nombre '{new_name}'.",
            )
        changes["name"] = new_name

    if "region" in changes and changes["region"] is not None:
        changes["region"] = changes["region"].strip()

    for field, value in changes.items():
        setattr(country, field, value)

    await db.flush()
    record_audit_log(
        db,
        actor_user_id=actor.id,
        action="catalogs.country_update",
        entity_type="country",
        entity_id=country.code,
        changes_payload={"updated_fields": sorted(changes.keys())},
        ip_address=ip_address,
    )
    return country


# =============================================================================
# AÑOS FISCALES (FiscalYear)
# =============================================================================


async def list_fiscal_years(db: AsyncSession) -> list[FiscalYear]:
    """Lista los años fiscales ordenados del más reciente al más antiguo."""
    stmt = select(FiscalYear).order_by(FiscalYear.start_date.desc())
    result = await db.scalars(stmt)
    return list(result.all())


async def get_current_fiscal_year(db: AsyncSession) -> FiscalYear:
    fy = await db.scalar(select(FiscalYear).where(FiscalYear.is_current.is_(True)))
    if fy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hay ningún año fiscal marcado como vigente actualmente.",
        )
    return fy


async def create_fiscal_year(
    db: AsyncSession,
    payload: FiscalYearCreate,
    actor: User,
    ip_address: str | None = None,
) -> FiscalYear:
    """
    Crea un nuevo año fiscal. Si `is_current=True`, desmarca automáticamente
    los demás años fiscales para mantener un único período vigente.
    """
    code = payload.code.strip().upper()
    duplicate = await db.scalar(select(FiscalYear.id).where(FiscalYear.code == code))
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un año fiscal con el código '{code}'.",
        )

    if payload.is_current:
        await db.execute(update(FiscalYear).values(is_current=False))

    fy = FiscalYear(
        code=code,
        start_date=payload.start_date,
        end_date=payload.end_date,
        is_current=payload.is_current,
    )
    db.add(fy)
    await db.flush()

    record_audit_log(
        db,
        actor_user_id=actor.id,
        action="catalogs.fiscal_year_create",
        entity_type="fiscal_year",
        entity_id=fy.id,
        changes_payload={
            "code": fy.code,
            "start_date": fy.start_date.isoformat(),
            "end_date": fy.end_date.isoformat(),
            "is_current": fy.is_current,
        },
        ip_address=ip_address,
    )
    return fy


async def update_fiscal_year(
    db: AsyncSession,
    fiscal_year_id: uuid.UUID,
    payload: FiscalYearUpdate,
    actor: User,
    ip_address: str | None = None,
) -> FiscalYear:
    fy = await db.scalar(select(FiscalYear).where(FiscalYear.id == fiscal_year_id))
    if fy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Año fiscal no encontrado.",
        )

    changes = payload.model_dump(exclude_unset=True)
    if "code" in changes and changes["code"] is not None:
        new_code = changes["code"].strip().upper()
        duplicate = await db.scalar(
            select(FiscalYear.id).where(
                FiscalYear.code == new_code, FiscalYear.id != fiscal_year_id
            )
        )
        if duplicate is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ya existe otro año fiscal con el código '{new_code}'.",
            )
        changes["code"] = new_code

    effective_start = changes.get("start_date", fy.start_date)
    effective_end = changes.get("end_date", fy.end_date)
    if effective_end <= effective_start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_date debe ser estrictamente posterior a start_date.",
        )

    if changes.get("is_current") is True:
        await db.execute(
            update(FiscalYear)
            .where(FiscalYear.id != fiscal_year_id)
            .values(is_current=False)
        )

    for field, value in changes.items():
        setattr(fy, field, value)

    await db.flush()
    record_audit_log(
        db,
        actor_user_id=actor.id,
        action="catalogs.fiscal_year_update",
        entity_type="fiscal_year",
        entity_id=fy.id,
        changes_payload={"updated_fields": sorted(changes.keys())},
        ip_address=ip_address,
    )
    return fy


# =============================================================================
# TAXONOMÍA COMERCIAL (Department > Category > Subcategory)
# =============================================================================


async def get_taxonomy_tree(
    db: AsyncSession,
    active_only: bool = True,
) -> list[Department]:
    """
    Devuelve la jerarquía completa Department > Category > Subcategory
    usando carga ansiosa (selectinload) para evitar consultas N+1.
    """
    stmt = (
        select(Department)
        .options(
            selectinload(Department.categories).selectinload(Category.subcategories)
        )
        .order_by(Department.code.asc())
    )
    if active_only:
        stmt = stmt.where(Department.is_active.is_(True))

    departments = list((await db.scalars(stmt)).all())
    if active_only:
        for dept in departments:
            dept.categories = [
                cat for cat in dept.categories if cat.is_active
            ]
            for cat in dept.categories:
                cat.subcategories = [
                    sub for sub in cat.subcategories if sub.is_active
                ]
    return departments


async def create_department(
    db: AsyncSession,
    payload: DepartmentCreate,
    actor: User,
    ip_address: str | None = None,
) -> Department:
    """Crea un nuevo departamento validando unicidad de código y nombre."""
    code = payload.code.strip().upper()
    name = payload.name.strip()

    existing = await db.scalar(
        select(Department.id).where(
            (Department.code == code) | (Department.name == name)
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un departamento con código '{code}' o nombre '{name}'.",
        )

    dept = Department(code=code, name=name, is_active=payload.is_active)
    db.add(dept)
    await db.flush()

    record_audit_log(
        db,
        actor_user_id=actor.id,
        action="catalogs.department_create",
        entity_type="department",
        entity_id=dept.id,
        changes_payload={"code": dept.code, "name": dept.name},
        ip_address=ip_address,
    )
    return dept


async def update_department(
    db: AsyncSession,
    department_id: uuid.UUID,
    payload: DepartmentUpdate,
    actor: User,
    ip_address: str | None = None,
) -> Department:
    dept = await db.scalar(select(Department).where(Department.id == department_id))
    if dept is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Departamento no encontrado.",
        )

    changes = payload.model_dump(exclude_unset=True)
    if "code" in changes and changes["code"] is not None:
        new_code = changes["code"].strip().upper()
        dup = await db.scalar(
            select(Department.id).where(
                Department.code == new_code, Department.id != department_id
            )
        )
        if dup is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ya existe otro departamento con código '{new_code}'.",
            )
        changes["code"] = new_code

    if "name" in changes and changes["name"] is not None:
        new_name = changes["name"].strip()
        dup = await db.scalar(
            select(Department.id).where(
                Department.name == new_name, Department.id != department_id
            )
        )
        if dup is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ya existe otro departamento con nombre '{new_name}'.",
            )
        changes["name"] = new_name

    for field, value in changes.items():
        setattr(dept, field, value)

    await db.flush()
    record_audit_log(
        db,
        actor_user_id=actor.id,
        action="catalogs.department_update",
        entity_type="department",
        entity_id=dept.id,
        changes_payload={"updated_fields": sorted(changes.keys())},
        ip_address=ip_address,
    )
    return dept


async def create_category(
    db: AsyncSession,
    payload: CategoryCreate,
    actor: User,
    ip_address: str | None = None,
) -> Category:
    """Crea una categoría (con su ProductClassification) bajo un departamento existente."""
    dept_exists = await db.scalar(
        select(Department.id).where(Department.id == payload.department_id)
    )
    if dept_exists is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El departamento especificado no existe.",
        )

    code = payload.code.strip().upper()
    duplicate = await db.scalar(
        select(Category.id).where(
            Category.department_id == payload.department_id,
            Category.code == code,
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe la categoría '{code}' en este departamento.",
        )

    category = Category(
        department_id=payload.department_id,
        code=code,
        name=payload.name.strip(),
        classification=payload.classification,
        is_active=payload.is_active,
    )
    db.add(category)
    await db.flush()

    record_audit_log(
        db,
        actor_user_id=actor.id,
        action="catalogs.category_create",
        entity_type="category",
        entity_id=category.id,
        changes_payload={
            "department_id": str(category.department_id),
            "code": category.code,
            "classification": category.classification.value,
        },
        ip_address=ip_address,
    )
    return category


async def update_category(
    db: AsyncSession,
    category_id: uuid.UUID,
    payload: CategoryUpdate,
    actor: User,
    ip_address: str | None = None,
) -> Category:
    category = await db.scalar(select(Category).where(Category.id == category_id))
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Categoría no encontrada.",
        )

    changes = payload.model_dump(exclude_unset=True)
    target_dept_id = changes.get("department_id", category.department_id)
    if "department_id" in changes and changes["department_id"] is not None:
        dept_exists = await db.scalar(
            select(Department.id).where(Department.id == target_dept_id)
        )
        if dept_exists is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="El departamento especificado no existe.",
            )

    target_code = (
        changes["code"].strip().upper()
        if "code" in changes and changes["code"] is not None
        else category.code
    )
    if "code" in changes and changes["code"] is not None:
        changes["code"] = target_code

    if "department_id" in changes or "code" in changes:
        dup = await db.scalar(
            select(Category.id).where(
                Category.department_id == target_dept_id,
                Category.code == target_code,
                Category.id != category_id,
            )
        )
        if dup is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ya existe la categoría '{target_code}' en ese departamento.",
            )

    if "name" in changes and changes["name"] is not None:
        changes["name"] = changes["name"].strip()

    for field, value in changes.items():
        setattr(category, field, value)

    await db.flush()
    record_audit_log(
        db,
        actor_user_id=actor.id,
        action="catalogs.category_update",
        entity_type="category",
        entity_id=category.id,
        changes_payload={"updated_fields": sorted(changes.keys())},
        ip_address=ip_address,
    )
    return category


async def create_subcategory(
    db: AsyncSession,
    payload: SubcategoryCreate,
    actor: User,
    ip_address: str | None = None,
) -> Subcategory:
    """Crea una subcategoría hoja bajo una categoría existente."""
    cat_exists = await db.scalar(
        select(Category.id).where(Category.id == payload.category_id)
    )
    if cat_exists is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La categoría especificada no existe.",
        )

    code = payload.code.strip().upper()
    duplicate = await db.scalar(
        select(Subcategory.id).where(
            Subcategory.category_id == payload.category_id,
            Subcategory.code == code,
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe la subcategoría '{code}' en esta categoría.",
        )

    subcategory = Subcategory(
        category_id=payload.category_id,
        code=code,
        name=payload.name.strip(),
        hs_chapter_hint=payload.hs_chapter_hint,
        requires_sanitary_reg=payload.requires_sanitary_reg,
        is_active=payload.is_active,
    )
    db.add(subcategory)
    await db.flush()

    record_audit_log(
        db,
        actor_user_id=actor.id,
        action="catalogs.subcategory_create",
        entity_type="subcategory",
        entity_id=subcategory.id,
        changes_payload={
            "category_id": str(subcategory.category_id),
            "code": subcategory.code,
            "name": subcategory.name,
        },
        ip_address=ip_address,
    )
    return subcategory


async def update_subcategory(
    db: AsyncSession,
    subcategory_id: uuid.UUID,
    payload: SubcategoryUpdate,
    actor: User,
    ip_address: str | None = None,
) -> Subcategory:
    subcategory = await db.scalar(
        select(Subcategory).where(Subcategory.id == subcategory_id)
    )
    if subcategory is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subcategoría no encontrada.",
        )

    changes = payload.model_dump(exclude_unset=True)
    target_cat_id = changes.get("category_id", subcategory.category_id)
    if "category_id" in changes and changes["category_id"] is not None:
        cat_exists = await db.scalar(
            select(Category.id).where(Category.id == target_cat_id)
        )
        if cat_exists is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="La categoría especificada no existe.",
            )

    target_code = (
        changes["code"].strip().upper()
        if "code" in changes and changes["code"] is not None
        else subcategory.code
    )
    if "code" in changes and changes["code"] is not None:
        changes["code"] = target_code

    if "category_id" in changes or "code" in changes:
        dup = await db.scalar(
            select(Subcategory.id).where(
                Subcategory.category_id == target_cat_id,
                Subcategory.code == target_code,
                Subcategory.id != subcategory_id,
            )
        )
        if dup is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ya existe la subcategoría '{target_code}' en esa categoría.",
            )

    if "name" in changes and changes["name"] is not None:
        changes["name"] = changes["name"].strip()

    for field, value in changes.items():
        setattr(subcategory, field, value)

    await db.flush()
    record_audit_log(
        db,
        actor_user_id=actor.id,
        action="catalogs.subcategory_update",
        entity_type="subcategory",
        entity_id=subcategory.id,
        changes_payload={"updated_fields": sorted(changes.keys())},
        ip_address=ip_address,
    )
    return subcategory
