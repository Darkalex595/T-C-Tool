from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_db
from backend.models import OriginScope, User
from backend.schemas.compliance import CertificationRead, CertificationUpdate
from backend.schemas.requests import PaginatedResponse
from backend.security import get_current_user, require_permissions
from backend.services import compliance as compliance_service

router = APIRouter(prefix="/certifications", tags=["Item Certifications"])


@router.get("", response_model=PaginatedResponse[CertificationRead])
async def list_certifications(
    req_general_id: UUID | None = Query(default=None),
    country_code: str | None = Query(default=None, min_length=2, max_length=2),
    origin_scope: OriginScope | None = Query(default=None),
    is_mandatory: bool | None = Query(default=None),
    search: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> PaginatedResponse[CertificationRead]:
    """Consulta paginada y filtrable de certificaciones requeridas a nivel global o por solicitud."""
    items, total = await compliance_service.list_certifications(
        db,
        req_general_id=req_general_id,
        country_code=country_code,
        origin_scope=origin_scope,
        is_mandatory=is_mandatory,
        search=search,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse(
        items=[CertificationRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{certification_id}", response_model=CertificationRead)
async def get_certification(
    certification_id: UUID,
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> CertificationRead:
    """Obtiene el detalle de una certificación específica por su UUID."""
    cert = await compliance_service.get_certification(db, certification_id)
    return CertificationRead.model_validate(cert)


@router.patch("/{certification_id}", response_model=CertificationRead)
async def update_certification(
    certification_id: UUID,
    payload: CertificationUpdate,
    request: Request,
    current_user: User = Depends(require_permissions("requests:assess")),
    db: AsyncSession = Depends(get_async_db),
) -> CertificationRead:
    cert = await compliance_service.update_certification(
        db,
        certification_id,
        payload,
        actor=current_user,
        ip_address=request.client.host if request.client else None,
    )
    return CertificationRead.model_validate(cert)


@router.delete("/{certification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_certification(
    certification_id: UUID,
    request: Request,
    current_user: User = Depends(require_permissions("requests:assess")),
    db: AsyncSession = Depends(get_async_db),
) -> Response:
    await compliance_service.delete_certification(
        db,
        certification_id,
        actor=current_user,
        ip_address=request.client.host if request.client else None,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
