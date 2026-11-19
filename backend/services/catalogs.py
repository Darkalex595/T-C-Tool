from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import Category, Country, Department, FiscalYear, Subcategory, User
from backend.schemas.catalogs import CategoryCreate, DepartmentCreate, SubcategoryCreate
from backend.services.audit import record_audit_log


async def list_countries(db: AsyncSession, active_only: bool = True) -> list[Country]:
    """Lista el catálogo de países ordenados alfabéticamente."""
    stmt = select(Country).order_by(Country.name.asc())
    if active_only:
        stmt = stmt.where(Country.is_active.is_(True))
    result = await db.scalars(stmt)
    return list(result.all())


async def list_fiscal_years(db: AsyncSession) -> list[FiscalYear]:
    """Lista los años fiscales ordenados del más reciente al más antiguo."""
    stmt = select(FiscalYear).order_by(FiscalYear.start_date.desc())
    result = await db.scalars(stmt)
    return list(result.all())


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
