from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from backend.models import (
    AssessmentDecision,
    Category,
    Country,
    FiscalYear,
    ImportAssessment,
    ImportRoute,
    ReqFood,
    ReqGeneral,
    ReqNoFood,
    ReqPlantApproval,
    ReqProduce,
    RequestBranchType,
    RequestStatus,
    Subcategory,
    User,
)
from backend.schemas.requests import (
    ImportAssessmentUpsert,
    ReqGeneralCreate,
    ReqGeneralStatusUpdate,
    ReqGeneralUpdate,
)
from backend.services.audit import record_audit_log


def _summary_load_options() -> list:
    """Opciones de carga ansiosa para listados de solicitudes sin errores MissingGreenlet."""
    return [
        joinedload(ReqGeneral.subcategory)
        .joinedload(Subcategory.category)
        .joinedload(Category.department),
        selectinload(ReqGeneral.destination_countries),
        joinedload(ReqGeneral.created_by),
        joinedload(ReqGeneral.assigned_to),
    ]


def _detail_load_options() -> list:
    """Opciones de carga completa (extensión 1:1, ruta, certificaciones y dictámenes)."""
    return [
        *_summary_load_options(),
        joinedload(ReqGeneral.import_route),
        joinedload(ReqGeneral.food_detail),
        joinedload(ReqGeneral.no_food_detail),
        joinedload(ReqGeneral.produce_detail),
        joinedload(ReqGeneral.plant_approval_detail),
        selectinload(ReqGeneral.certifications),
        selectinload(ReqGeneral.assessments).joinedload(ImportAssessment.reviewer),
    ]


async def list_requests(
    db: AsyncSession,
    *,
    status_filter: RequestStatus | None = None,
    branch_type: RequestBranchType | None = None,
    country_code: str | None = None,
    is_urgent: bool | None = None,
    search: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[ReqGeneral], int]:
    filters = []
    if status_filter is not None:
        filters.append(ReqGeneral.status == status_filter)
    if branch_type is not None:
        filters.append(ReqGeneral.branch_type == branch_type)
    if is_urgent is not None:
        filters.append(ReqGeneral.is_urgent.is_(is_urgent))
    if country_code:
        code = country_code.strip().upper()
        filters.append(ReqGeneral.destination_countries.any(Country.code == code))
    if search and search.strip():
        term = f"%{search.strip()}%"
        filters.append(
            or_(
                ReqGeneral.item_description.ilike(term),
                ReqGeneral.item_code.ilike(term),
                ReqGeneral.vendor_name.ilike(term),
                ReqGeneral.hs_code_proposed.ilike(term),
            )
        )

    total = int(await db.scalar(select(func.count(ReqGeneral.id)).where(*filters)) or 0)

    stmt = (
        select(ReqGeneral)
        .options(*_summary_load_options())
        .where(*filters)
        .order_by(ReqGeneral.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = list((await db.scalars(stmt)).unique().all())
    return items, total


async def get_request_detail(db: AsyncSession, request_id: uuid.UUID) -> ReqGeneral:
    stmt = (
        select(ReqGeneral)
        .options(*_detail_load_options())
        .where(ReqGeneral.id == request_id)
    )
    req = await db.scalar(stmt)
    if req is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Solicitud no encontrada.",
        )
    return req


async def create_request(
    db: AsyncSession,
    payload: ReqGeneralCreate,
    actor: User,
    ip_address: str | None = None,
) -> ReqGeneral:
    """
    Crea de forma atómica `ReqGeneral`, sus países destino M2M y su tabla hija 1:1
    correspondiente al `branch_type`, registrando además la auditoría inicial.
    """
    subcategory = await db.scalar(
        select(Subcategory).where(Subcategory.id == payload.subcategory_id)
    )
    if subcategory is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La subcategoría seleccionada no existe.",
        )

    if payload.fiscal_year_id is not None:
        fy_exists = await db.scalar(
            select(FiscalYear.id).where(FiscalYear.id == payload.fiscal_year_id)
        )
        if fy_exists is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El año fiscal especificado no existe.",
            )

    if payload.import_route_id is not None:
        route_exists = await db.scalar(
            select(ImportRoute.id).where(ImportRoute.id == payload.import_route_id)
        )
        if route_exists is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La ruta logística especificada no existe.",
            )

    if payload.assigned_to_id is not None:
        assignee_exists = await db.scalar(
            select(User.id).where(User.id == payload.assigned_to_id)
        )
        if assignee_exists is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El usuario asignado no existe.",
            )

    # Validar países de proveedor, origen y destinos en una sola consulta
    all_country_codes = set(payload.destination_country_codes) | {
        payload.vendor_country_code,
        payload.origin_country_code,
    }
    found_countries = {
        c.code: c
        for c in (
            await db.scalars(select(Country).where(Country.code.in_(all_country_codes)))
        ).all()
    }
    missing_codes = sorted(all_country_codes - found_countries.keys())
    if missing_codes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Códigos de país no registrados: {', '.join(missing_codes)}.",
        )

    req = ReqGeneral(
        request_type=payload.request_type,
        branch_type=payload.branch_type,
        status=RequestStatus.PENDING,
        is_urgent=payload.is_urgent,
        fiscal_year_id=payload.fiscal_year_id,
        subcategory_id=payload.subcategory_id,
        import_route_id=payload.import_route_id,
        item_code=payload.item_code,
        item_description=payload.item_description.strip(),
        brand_name=payload.brand_name,
        vendor_name=payload.vendor_name.strip(),
        vendor_country_code=payload.vendor_country_code,
        origin_country_code=payload.origin_country_code,
        hs_code_proposed=payload.hs_code_proposed,
        comments=payload.comments,
        created_by_id=actor.id,
        assigned_to_id=payload.assigned_to_id,
        sla_due_at=payload.sla_due_at,
        destination_countries=[
            found_countries[code] for code in payload.destination_country_codes
        ],
    )

    # Instanciar extensión 1:1 (Shared Primary Key gestionado automáticamente por SQLAlchemy)
    if payload.branch_type == RequestBranchType.FOOD and payload.food_detail is not None:
        req.food_detail = ReqFood(**payload.food_detail.model_dump())
    elif (
        payload.branch_type == RequestBranchType.NO_FOOD
        and payload.no_food_detail is not None
    ):
        req.no_food_detail = ReqNoFood(**payload.no_food_detail.model_dump())
    elif (
        payload.branch_type == RequestBranchType.PRODUCE
        and payload.produce_detail is not None
    ):
        req.produce_detail = ReqProduce(**payload.produce_detail.model_dump())
    elif (
        payload.branch_type == RequestBranchType.PLANT_APPROVAL
        and payload.plant_approval_detail is not None
    ):
        req.plant_approval_detail = ReqPlantApproval(
            **payload.plant_approval_detail.model_dump()
        )

    db.add(req)
    await db.flush()

    record_audit_log(
        db,
        actor_user_id=actor.id,
        action="requests.create",
        entity_type="req_general",
        entity_id=req.id,
        changes_payload={
            "ticket_number": req.ticket_number,
            "branch_type": req.branch_type.value,
            "subcategory_id": str(req.subcategory_id),
            "destinations": payload.destination_country_codes,
        },
        ip_address=ip_address,
    )

    return await get_request_detail(db, req.id)


async def update_request(
    db: AsyncSession,
    request_id: uuid.UUID,
    payload: ReqGeneralUpdate,
    actor: User,
    ip_address: str | None = None,
) -> ReqGeneral:
    req = await get_request_detail(db, request_id)
    changes = payload.model_dump(exclude_unset=True)

    if "subcategory_id" in changes and changes["subcategory_id"] is not None:
        sub_exists = await db.scalar(
            select(Subcategory.id).where(Subcategory.id == changes["subcategory_id"])
        )
        if sub_exists is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La subcategoría especificada no existe.",
            )

    if "import_route_id" in changes and changes["import_route_id"] is not None:
        route_exists = await db.scalar(
            select(ImportRoute.id).where(ImportRoute.id == changes["import_route_id"])
        )
        if route_exists is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La ruta logística especificada no existe.",
            )

    if "assigned_to_id" in changes and changes["assigned_to_id"] is not None:
        user_exists = await db.scalar(
            select(User.id).where(User.id == changes["assigned_to_id"])
        )
        if user_exists is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El usuario asignado no existe.",
            )

    for field, value in changes.items():
        setattr(req, field, value)

    await db.flush()
    record_audit_log(
        db,
        actor_user_id=actor.id,
        action="requests.update",
        entity_type="req_general",
        entity_id=req.id,
        changes_payload={"updated_fields": sorted(changes.keys())},
        ip_address=ip_address,
    )
    return await get_request_detail(db, req.id)


async def change_request_status(
    db: AsyncSession,
    request_id: uuid.UUID,
    payload: ReqGeneralStatusUpdate,
    actor: User,
    ip_address: str | None = None,
) -> ReqGeneral:
    """Actualiza el estado global de la solicitud y gestiona la marca `closed_at`."""
    req = await get_request_detail(db, request_id)
    previous_status = req.status
    req.status = payload.status

    if payload.comments is not None:
        req.comments = payload.comments

    if payload.status in {RequestStatus.COMPLETED, RequestStatus.CANCELED}:
        req.closed_at = datetime.now(timezone.utc)
    else:
        req.closed_at = None

    await db.flush()
    record_audit_log(
        db,
        actor_user_id=actor.id,
        action="requests.status_change",
        entity_type="req_general",
        entity_id=req.id,
        changes_payload={
            "ticket_number": req.ticket_number,
            "from": previous_status.value,
            "to": payload.status.value,
        },
        ip_address=ip_address,
    )
    return await get_request_detail(db, req.id)


async def upsert_assessment(
    db: AsyncSession,
    request_id: uuid.UUID,
    payload: ImportAssessmentUpsert,
    actor: User,
    ip_address: str | None = None,
) -> ImportAssessment:
    """
    Crea o actualiza el dictamen técnico (`ImportAssessment`) para un país destino
    específico de la solicitud, avanzando `Pending -> In Progress` automáticamente.
    """
    req = await get_request_detail(db, request_id)
    destination_codes = {c.code for c in req.destination_countries}
    if payload.country_code not in destination_codes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"El país '{payload.country_code}' no forma parte de los países destino "
                f"de esta solicitud ({', '.join(sorted(destination_codes))})."
            ),
        )

    assessment = await db.scalar(
        select(ImportAssessment)
        .options(joinedload(ImportAssessment.reviewer))
        .where(
            ImportAssessment.req_general_id == request_id,
            ImportAssessment.country_code == payload.country_code,
        )
    )

    now = datetime.now(timezone.utc)
    is_new = assessment is None

    if assessment is None:
        assessment = ImportAssessment(
            req_general_id=request_id,
            country_code=payload.country_code,
        )
        db.add(assessment)

    assessment.reviewer_id = actor.id
    assessment.decision = payload.decision
    assessment.hs_tariff_confirmed = payload.hs_tariff_confirmed
    assessment.import_duty_rate = payload.import_duty_rate
    assessment.estimated_lead_time_days = payload.estimated_lead_time_days
    assessment.requires_import_permit = payload.requires_import_permit
    assessment.requires_sanitary_registration = payload.requires_sanitary_registration
    assessment.required_certificates = payload.required_certificates
    assessment.category_checklist = payload.category_checklist
    assessment.technical_notes = payload.technical_notes
    assessment.assessed_at = (
        now if payload.decision != AssessmentDecision.PENDING else None
    )

    if req.status == RequestStatus.PENDING:
        req.status = RequestStatus.IN_PROGRESS

    await db.flush()

    record_audit_log(
        db,
        actor_user_id=actor.id,
        action="assessments.create" if is_new else "assessments.update",
        entity_type="import_assessment",
        entity_id=assessment.id,
        changes_payload={
            "req_general_id": str(request_id),
            "country_code": payload.country_code,
            "decision": payload.decision.value,
        },
        ip_address=ip_address,
    )

    loaded = await db.scalar(
        select(ImportAssessment)
        .options(joinedload(ImportAssessment.reviewer))
        .where(ImportAssessment.id == assessment.id)
    )
    assert loaded is not None
    return loaded
