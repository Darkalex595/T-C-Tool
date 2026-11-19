from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_db
from backend.models import RequestBranchType, RequestStatus, User
from backend.schemas.compliance import CertificationCreate, CertificationRead
from backend.schemas.requests import (
    ImportAssessmentRead,
    ImportAssessmentUpsert,
    PaginatedResponse,
    ReqGeneralCreate,
    ReqGeneralDetailRead,
    ReqGeneralStatusUpdate,
    ReqGeneralSummaryRead,
    ReqGeneralUpdate,
)
from backend.security import get_current_user, require_permissions
from backend.services import compliance as compliance_service
from backend.services import requests as request_service

router = APIRouter(prefix="/requests", tags=["Compliance Requests"])


@router.get("", response_model=PaginatedResponse[ReqGeneralSummaryRead])
async def list_requests(
    status_filter: RequestStatus | None = Query(default=None, alias="status"),
    branch_type: RequestBranchType | None = Query(default=None),
    country_code: str | None = Query(default=None, min_length=2, max_length=2),
    is_urgent: bool | None = Query(default=None),
    search: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> PaginatedResponse[ReqGeneralSummaryRead]:
    """Listado paginado y filtrable de solicitudes de cumplimiento."""
    items, total = await request_service.list_requests(
        db,
        status_filter=status_filter,
        branch_type=branch_type,
        country_code=country_code,
        is_urgent=is_urgent,
        search=search,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse(
        items=[ReqGeneralSummaryRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{request_id}", response_model=ReqGeneralDetailRead)
async def get_request_detail(
    request_id: UUID,
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> ReqGeneralDetailRead:
    """Devuelve el detalle completo de una solicitud con extensión 1:1, certificaciones y dictámenes."""
    req = await request_service.get_request_detail(db, request_id)
    return ReqGeneralDetailRead.model_validate(req)


@router.post(
    "",
    response_model=ReqGeneralDetailRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_request(
    payload: ReqGeneralCreate,
    request: Request,
    current_user: User = Depends(require_permissions("requests:create")),
    db: AsyncSession = Depends(get_async_db),
) -> ReqGeneralDetailRead:
    """Crea atómicamente una solicitud con su extensión 1:1 y países destino."""
    req = await request_service.create_request(
        db,
        payload,
        actor=current_user,
        ip_address=request.client.host if request.client else None,
    )
    return ReqGeneralDetailRead.model_validate(req)


@router.patch("/{request_id}", response_model=ReqGeneralDetailRead)
async def update_request(
    request_id: UUID,
    payload: ReqGeneralUpdate,
    request: Request,
    current_user: User = Depends(require_permissions("requests:create")),
    db: AsyncSession = Depends(get_async_db),
) -> ReqGeneralDetailRead:
    req = await request_service.update_request(
        db,
        request_id,
        payload,
        actor=current_user,
        ip_address=request.client.host if request.client else None,
    )
    return ReqGeneralDetailRead.model_validate(req)


@router.patch("/{request_id}/status", response_model=ReqGeneralDetailRead)
async def update_request_status(
    request_id: UUID,
    payload: ReqGeneralStatusUpdate,
    request: Request,
    current_user: User = Depends(require_permissions("requests:approve")),
    db: AsyncSession = Depends(get_async_db),
) -> ReqGeneralDetailRead:
    """Actualiza el estado global (Pending / In Progress / Partially Finished / Completed / Canceled)."""
    req = await request_service.change_request_status(
        db,
        request_id,
        payload,
        actor=current_user,
        ip_address=request.client.host if request.client else None,
    )
    return ReqGeneralDetailRead.model_validate(req)


@router.put("/{request_id}/assessments", response_model=ImportAssessmentRead)
async def upsert_request_assessment(
    request_id: UUID,
    payload: ImportAssessmentUpsert,
    request: Request,
    current_user: User = Depends(require_permissions("requests:assess")),
    db: AsyncSession = Depends(get_async_db),
) -> ImportAssessmentRead:
    """Crea o actualiza el dictamen técnico de importación para un país destino de la solicitud."""
    assessment = await request_service.upsert_assessment(
        db,
        request_id,
        payload,
        actor=current_user,
        ip_address=request.client.host if request.client else None,
    )
    return ImportAssessmentRead.model_validate(assessment)


@router.get("/{request_id}/certifications", response_model=list[CertificationRead])
async def list_request_certifications(
    request_id: UUID,
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> list[CertificationRead]:
    """Lista las certificaciones requeridas ligadas directamente a este ítem/solicitud."""
    certs = await compliance_service.list_request_certifications(db, request_id)
    return [CertificationRead.model_validate(c) for c in certs]


@router.post(
    "/{request_id}/certifications",
    response_model=CertificationRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_request_certification(
    request_id: UUID,
    payload: CertificationCreate,
    request: Request,
    current_user: User = Depends(require_permissions("requests:assess")),
    db: AsyncSession = Depends(get_async_db),
) -> CertificationRead:
    """Agrega un certificado requerido directamente al ítem consultado."""
    cert = await compliance_service.add_request_certification(
        db,
        request_id,
        payload,
        actor=current_user,
        ip_address=request.client.host if request.client else None,
    )
    return CertificationRead.model_validate(cert)
