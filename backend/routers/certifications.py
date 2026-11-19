from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_db
from backend.models import User
from backend.schemas.compliance import CertificationRead, CertificationUpdate
from backend.security import require_permissions
from backend.services import compliance as compliance_service

router = APIRouter(prefix="/certifications", tags=["Item Certifications"])


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
