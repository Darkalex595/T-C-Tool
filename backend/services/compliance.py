from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import (
    CertificationRequirement,
    Country,
    Department,
    ImportRoute,
    LogisticsRouteCode,
    OriginScope,
    ProductClassification,
    Regulation,
    RegulationStatus,
    ReqGeneral,
    Subcategory,
    User,
)
from backend.schemas.compliance import (
    CertificationCreate,
    CertificationUpdate,
    ImportRouteCreate,
    ImportRouteUpdate,
    RegulationCreate,
    RegulationUpdate,
)
from backend.services.audit import record_audit_log


async def _ensure_country_exists(db: AsyncSession, country_code: str) -> str:
    code = country_code.strip().upper()
    exists = await db.scalar(select(Country.code).where(Country.code == code))
    if exists is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El código de país '{code}' no existe en el catálogo.",
        )
    return code


# =============================================================================
# RUTAS LOGÍSTICAS (ImportRoute)
# =============================================================================


async def list_import_routes(
    db: AsyncSession,
    *,
    country_code: str | None = None,
    classification: ProductClassification | None = None,
    route_code: LogisticsRouteCode | None = None,
    search: str | None = None,
    active_only: bool = True,
) -> list[ImportRoute]:
    stmt = select(ImportRoute).order_by(ImportRoute.dc_code.asc())
    if active_only:
        stmt = stmt.where(ImportRoute.is_active.is_(True))
    if country_code:
        code = country_code.strip().upper()
        # Incluye rutas específicas del país y rutas globales (country_code IS NULL)
        stmt = stmt.where(
            (ImportRoute.country_code == code) | (ImportRoute.country_code.is_(None))
        )
    if classification:
        stmt = stmt.where(
            (ImportRoute.classification == classification)
            | (ImportRoute.classification == ProductClassification.ALL)
            | (ImportRoute.classification.is_(None))
        )
    if route_code:
        stmt = stmt.where(ImportRoute.route_code == route_code)
    if search and search.strip():
        term = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                ImportRoute.dc_code.ilike(term),
                ImportRoute.route_name.ilike(term),
                ImportRoute.required_document.ilike(term),
            )
        )
    return list((await db.scalars(stmt)).all())


async def get_import_route(db: AsyncSession, route_id: uuid.UUID) -> ImportRoute:
    route = await db.scalar(select(ImportRoute).where(ImportRoute.id == route_id))
    if route is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ruta logística no encontrada.",
        )
    return route


async def create_import_route(
    db: AsyncSession,
    payload: ImportRouteCreate,
    actor: User,
    ip_address: str | None = None,
) -> ImportRoute:
    if payload.country_code:
        await _ensure_country_exists(db, payload.country_code)

    dc_code = payload.dc_code.strip().upper()
    duplicate = await db.scalar(
        select(ImportRoute.id).where(
            ImportRoute.route_code == payload.route_code,
            ImportRoute.dc_code == dc_code,
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe una ruta '{payload.route_code.value}' con DC '{dc_code}'.",
        )

    route = ImportRoute(
        route_code=payload.route_code,
        route_name=payload.route_name.strip(),
        dc_code=dc_code,
        country_code=payload.country_code,
        classification=payload.classification,
        required_document=payload.required_document.strip(),
        description=payload.description,
        us_origin_rules=payload.us_origin_rules,
        non_us_origin_rules=payload.non_us_origin_rules,
        is_direct_to_destination=payload.is_direct_to_destination,
        is_active=payload.is_active,
    )
    db.add(route)
    await db.flush()

    record_audit_log(
        db,
        actor_user_id=actor.id,
        action="routes.create",
        entity_type="import_route",
        entity_id=route.id,
        changes_payload={"route_code": route.route_code.value, "dc_code": route.dc_code},
        ip_address=ip_address,
    )
    return route


async def update_import_route(
    db: AsyncSession,
    route_id: uuid.UUID,
    payload: ImportRouteUpdate,
    actor: User,
    ip_address: str | None = None,
) -> ImportRoute:
    route = await get_import_route(db, route_id)
    changes = payload.model_dump(exclude_unset=True)

    non_nullable_fields = {
        "route_name",
        "dc_code",
        "required_document",
        "is_direct_to_destination",
        "is_active",
    }
    for req_field in non_nullable_fields:
        if req_field in changes and changes[req_field] is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"El campo '{req_field}' no puede ser nulo.",
            )

    if "dc_code" in changes:
        new_dc = changes["dc_code"].strip().upper()
        if new_dc != route.dc_code:
            duplicate = await db.scalar(
                select(ImportRoute.id).where(
                    ImportRoute.route_code == route.route_code,
                    ImportRoute.dc_code == new_dc,
                    ImportRoute.id != route.id,
                )
            )
            if duplicate is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Ya existe una ruta '{route.route_code.value}' con DC '{new_dc}'.",
                )
        changes["dc_code"] = new_dc

    if "country_code" in changes and changes["country_code"] is not None:
        changes["country_code"] = await _ensure_country_exists(db, changes["country_code"])

    for field, value in changes.items():
        setattr(route, field, value)

    await db.flush()
    record_audit_log(
        db,
        actor_user_id=actor.id,
        action="routes.update",
        entity_type="import_route",
        entity_id=route.id,
        changes_payload={"updated_fields": sorted(changes.keys())},
        ip_address=ip_address,
    )
    return route


async def delete_import_route(
    db: AsyncSession,
    route_id: uuid.UUID,
    actor: User,
    ip_address: str | None = None,
) -> None:
    """Elimina una ruta logística si no tiene solicitudes asociadas (409 si está en uso)."""
    route = await get_import_route(db, route_id)
    in_use_count = int(
        await db.scalar(
            select(func.count(ReqGeneral.id)).where(
                ReqGeneral.import_route_id == route.id
            )
        )
        or 0
    )
    if in_use_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"La ruta '{route.dc_code}' está asociada a {in_use_count} solicitud(es). "
                "Desactívala con PATCH {'is_active': false} en lugar de eliminarla."
            ),
        )

    route_code_val = route.route_code.value
    dc_code_val = route.dc_code
    await db.delete(route)
    await db.flush()

    record_audit_log(
        db,
        actor_user_id=actor.id,
        action="routes.delete",
        entity_type="import_route",
        entity_id=route_id,
        changes_payload={"route_code": route_code_val, "dc_code": dc_code_val},
        ip_address=ip_address,
    )


# =============================================================================
# REGULACIONES MULTINACIONALES (Regulation)
# =============================================================================


async def list_regulations(
    db: AsyncSession,
    *,
    country_code: str | None = None,
    status_filter: RegulationStatus | None = None,
    department_id: uuid.UUID | None = None,
    subcategory_id: uuid.UUID | None = None,
    search: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Regulation], int]:
    filters = []
    if country_code:
        filters.append(Regulation.country_code == country_code.strip().upper())
    if status_filter:
        filters.append(Regulation.status == status_filter)
    if department_id:
        filters.append(Regulation.department_id == department_id)
    if subcategory_id:
        filters.append(Regulation.subcategories.any(Subcategory.id == subcategory_id))
    if search and search.strip():
        term = f"%{search.strip()}%"
        filters.append(
            or_(
                Regulation.regulation_code.ilike(term),
                Regulation.title.ilike(term),
                Regulation.issuing_authority.ilike(term),
                Regulation.summary.ilike(term),
            )
        )

    count_stmt = select(func.count(Regulation.id)).where(*filters)
    total = int(await db.scalar(count_stmt) or 0)

    stmt = (
        select(Regulation)
        .options(selectinload(Regulation.subcategories))
        .where(*filters)
        .order_by(Regulation.country_code.asc(), Regulation.regulation_code.asc())
        .limit(limit)
        .offset(offset)
    )
    items = list((await db.scalars(stmt)).all())
    return items, total


async def get_regulation(db: AsyncSession, regulation_id: uuid.UUID) -> Regulation:
    stmt = (
        select(Regulation)
        .options(selectinload(Regulation.subcategories))
        .where(Regulation.id == regulation_id)
    )
    regulation = await db.scalar(stmt)
    if regulation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Regulación no encontrada.",
        )
    return regulation


async def _load_subcategories_by_ids(
    db: AsyncSession, subcategory_ids: list[uuid.UUID]
) -> list[Subcategory]:
    if not subcategory_ids:
        return []
    unique_ids = list(dict.fromkeys(subcategory_ids))
    rows = list(
        (await db.scalars(select(Subcategory).where(Subcategory.id.in_(unique_ids)))).all()
    )
    if len(rows) != len(unique_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Una o más subcategorías especificadas no existen.",
        )
    return rows


async def create_regulation(
    db: AsyncSession,
    payload: RegulationCreate,
    actor: User,
    ip_address: str | None = None,
) -> Regulation:
    country_code = await _ensure_country_exists(db, payload.country_code)

    if payload.department_id is not None:
        dept_exists = await db.scalar(
            select(Department.id).where(Department.id == payload.department_id)
        )
        if dept_exists is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El departamento especificado no existe.",
            )

    reg_code = payload.regulation_code.strip()
    duplicate = await db.scalar(
        select(Regulation.id).where(
            Regulation.country_code == country_code,
            Regulation.regulation_code == reg_code,
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe la regulación '{reg_code}' para '{country_code}'.",
        )

    subcategories = await _load_subcategories_by_ids(db, payload.subcategory_ids)

    regulation = Regulation(
        country_code=country_code,
        department_id=payload.department_id,
        regulation_code=reg_code,
        title=payload.title.strip(),
        issuing_authority=payload.issuing_authority.strip(),
        status=payload.status,
        summary=payload.summary.strip(),
        requirements_detail=payload.requirements_detail,
        effective_date=payload.effective_date,
        expiration_date=payload.expiration_date,
        source_url=payload.source_url,
        metadata_extra=payload.metadata_extra,
        subcategories=subcategories,
        created_by_id=actor.id,
    )
    db.add(regulation)
    await db.flush()

    record_audit_log(
        db,
        actor_user_id=actor.id,
        action="regulations.create",
        entity_type="regulation",
        entity_id=regulation.id,
        changes_payload={
            "country_code": country_code,
            "regulation_code": reg_code,
            "status": regulation.status.value,
        },
        ip_address=ip_address,
    )
    return await get_regulation(db, regulation.id)


async def update_regulation(
    db: AsyncSession,
    regulation_id: uuid.UUID,
    payload: RegulationUpdate,
    actor: User,
    ip_address: str | None = None,
) -> Regulation:
    regulation = await get_regulation(db, regulation_id)
    changes = payload.model_dump(exclude_unset=True)

    non_nullable_fields = {"title", "issuing_authority", "status", "summary"}
    for req_field in non_nullable_fields:
        if req_field in changes and changes[req_field] is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"El campo '{req_field}' no puede ser nulo.",
            )

    final_effective = (
        changes["effective_date"]
        if "effective_date" in changes
        else regulation.effective_date
    )
    final_expiration = (
        changes["expiration_date"]
        if "expiration_date" in changes
        else regulation.expiration_date
    )
    if (
        final_effective is not None
        and final_expiration is not None
        and final_expiration < final_effective
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="expiration_date debe ser mayor o igual a effective_date.",
        )

    if "department_id" in changes and changes["department_id"] is not None:
        dept_exists = await db.scalar(
            select(Department.id).where(Department.id == changes["department_id"])
        )
        if dept_exists is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El departamento especificado no existe.",
            )

    if "subcategory_ids" in changes:
        sub_ids = changes.pop("subcategory_ids") or []
        regulation.subcategories = await _load_subcategories_by_ids(db, sub_ids)

    for field, value in changes.items():
        setattr(regulation, field, value)

    await db.flush()
    record_audit_log(
        db,
        actor_user_id=actor.id,
        action="regulations.update",
        entity_type="regulation",
        entity_id=regulation.id,
        changes_payload={
            "updated_fields": sorted(payload.model_dump(exclude_unset=True).keys())
        },
        ip_address=ip_address,
    )
    return await get_regulation(db, regulation.id)


async def delete_regulation(
    db: AsyncSession,
    regulation_id: uuid.UUID,
    actor: User,
    ip_address: str | None = None,
) -> None:
    """Elimina una regulación multinacional y registra la acción en auditoría."""
    regulation = await get_regulation(db, regulation_id)
    country_code = regulation.country_code
    reg_code = regulation.regulation_code

    await db.delete(regulation)
    await db.flush()

    record_audit_log(
        db,
        actor_user_id=actor.id,
        action="regulations.delete",
        entity_type="regulation",
        entity_id=regulation_id,
        changes_payload={
            "country_code": country_code,
            "regulation_code": reg_code,
        },
        ip_address=ip_address,
    )


# =============================================================================
# CERTIFICACIONES LIGADAS AL ÍTEM (CertificationRequirement -> ReqGeneral)
# =============================================================================


async def list_certifications(
    db: AsyncSession,
    *,
    req_general_id: uuid.UUID | None = None,
    country_code: str | None = None,
    origin_scope: OriginScope | None = None,
    is_mandatory: bool | None = None,
    search: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[CertificationRequirement], int]:
    """Listado global paginado y filtrable de certificaciones requeridas por ítem."""
    filters = []
    if req_general_id is not None:
        filters.append(CertificationRequirement.req_general_id == req_general_id)
    if country_code:
        filters.append(
            CertificationRequirement.country_code == country_code.strip().upper()
        )
    if origin_scope is not None:
        filters.append(CertificationRequirement.origin_scope == origin_scope)
    if is_mandatory is not None:
        filters.append(CertificationRequirement.is_mandatory.is_(is_mandatory))
    if search and search.strip():
        term = f"%{search.strip()}%"
        filters.append(
            or_(
                CertificationRequirement.certificate_name.ilike(term),
                CertificationRequirement.issuing_body.ilike(term),
                CertificationRequirement.notes.ilike(term),
            )
        )

    total = int(
        await db.scalar(select(func.count(CertificationRequirement.id)).where(*filters))
        or 0
    )
    stmt = (
        select(CertificationRequirement)
        .where(*filters)
        .order_by(CertificationRequirement.certificate_name.asc())
        .limit(limit)
        .offset(offset)
    )
    items = list((await db.scalars(stmt)).all())
    return items, total


async def get_certification(
    db: AsyncSession, certification_id: uuid.UUID
) -> CertificationRequirement:
    cert = await db.scalar(
        select(CertificationRequirement).where(
            CertificationRequirement.id == certification_id
        )
    )
    if cert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Certificación no encontrada.",
        )
    return cert


async def list_request_certifications(
    db: AsyncSession, request_id: uuid.UUID
) -> list[CertificationRequirement]:
    req_exists = await db.scalar(select(ReqGeneral.id).where(ReqGeneral.id == request_id))
    if req_exists is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Solicitud no encontrada.",
        )
    stmt = (
        select(CertificationRequirement)
        .where(CertificationRequirement.req_general_id == request_id)
        .order_by(CertificationRequirement.certificate_name.asc())
    )
    return list((await db.scalars(stmt)).all())


async def add_request_certification(
    db: AsyncSession,
    request_id: uuid.UUID,
    payload: CertificationCreate,
    actor: User,
    ip_address: str | None = None,
) -> CertificationRequirement:
    req_exists = await db.scalar(select(ReqGeneral.id).where(ReqGeneral.id == request_id))
    if req_exists is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Solicitud no encontrada.",
        )

    country_code: str | None = None
    if payload.country_code:
        country_code = await _ensure_country_exists(db, payload.country_code)

    cert = CertificationRequirement(
        req_general_id=request_id,
        country_code=country_code,
        origin_scope=payload.origin_scope,
        certificate_name=payload.certificate_name.strip(),
        issuing_body=payload.issuing_body,
        is_mandatory=payload.is_mandatory,
        requires_apostille=payload.requires_apostille,
        validity_days=payload.validity_days,
        notes=payload.notes,
    )
    db.add(cert)
    await db.flush()

    record_audit_log(
        db,
        actor_user_id=actor.id,
        action="certifications.create",
        entity_type="certification_requirement",
        entity_id=cert.id,
        changes_payload={
            "req_general_id": str(request_id),
            "country_code": country_code,
            "certificate_name": cert.certificate_name,
        },
        ip_address=ip_address,
    )
    return cert


async def update_certification(
    db: AsyncSession,
    certification_id: uuid.UUID,
    payload: CertificationUpdate,
    actor: User,
    ip_address: str | None = None,
) -> CertificationRequirement:
    cert = await get_certification(db, certification_id)

    changes = payload.model_dump(exclude_unset=True)
    non_nullable_fields = {
        "origin_scope",
        "certificate_name",
        "is_mandatory",
        "requires_apostille",
    }
    for req_field in non_nullable_fields:
        if req_field in changes and changes[req_field] is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"El campo '{req_field}' no puede ser nulo.",
            )

    if "country_code" in changes and changes["country_code"] is not None:
        changes["country_code"] = await _ensure_country_exists(db, changes["country_code"])

    for field, value in changes.items():
        setattr(cert, field, value)

    await db.flush()
    record_audit_log(
        db,
        actor_user_id=actor.id,
        action="certifications.update",
        entity_type="certification_requirement",
        entity_id=cert.id,
        changes_payload={"updated_fields": sorted(changes.keys())},
        ip_address=ip_address,
    )
    return cert


async def delete_certification(
    db: AsyncSession,
    certification_id: uuid.UUID,
    actor: User,
    ip_address: str | None = None,
) -> None:
    cert = await db.scalar(
        select(CertificationRequirement).where(
            CertificationRequirement.id == certification_id
        )
    )
    if cert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Certificación no encontrada.",
        )

    req_id = str(cert.req_general_id)
    cert_name = cert.certificate_name
    await db.delete(cert)
    await db.flush()

    record_audit_log(
        db,
        actor_user_id=actor.id,
        action="certifications.delete",
        entity_type="certification_requirement",
        entity_id=certification_id,
        changes_payload={"req_general_id": req_id, "certificate_name": cert_name},
        ip_address=ip_address,
    )
