from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_db
from backend.models import RegulationStatus, User
from backend.schemas.compliance import (
    RegulationCreate,
    RegulationRead,
    RegulationUpdate,
)
from backend.schemas.requests import PaginatedResponse
from backend.security import get_current_user, require_permissions
from backend.services import compliance as compliance_service

router = APIRouter(prefix="/regulations", tags=["Regulations"])


@router.get("", response_model=PaginatedResponse[RegulationRead])
async def list_regulations(
    country_code: str | None = Query(default=None, min_length=2, max_length=2),
    status_filter: RegulationStatus | None = Query(default=None, alias="status"),
    department_id: UUID | None = Query(default=None),
    subcategory_id: UUID | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> PaginatedResponse[RegulationRead]:
    """Consulta paginada de regulaciones multinacionales por país, estado o taxonomía."""
    items, total = await compliance_service.list_regulations(
        db,
        country_code=country_code,
        status_filter=status_filter,
        department_id=department_id,
        subcategory_id=subcategory_id,
        limit=limit,
        offset=offset,
    )
    return PaginatedResponse(
        items=[RegulationRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{regulation_id}", response_model=RegulationRead)
async def get_regulation(
    regulation_id: UUID,
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> RegulationRead:
    regulation = await compliance_service.get_regulation(db, regulation_id)
    return RegulationRead.model_validate(regulation)


@router.post(
    "",
    response_model=RegulationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_regulation(
    payload: RegulationCreate,
    request: Request,
    current_user: User = Depends(require_permissions("regulations:manage")),
    db: AsyncSession = Depends(get_async_db),
) -> RegulationRead:
    regulation = await compliance_service.create_regulation(
        db,
        payload,
        actor=current_user,
        ip_address=request.client.host if request.client else None,
    )
    return RegulationRead.model_validate(regulation)


@router.patch("/{regulation_id}", response_model=RegulationRead)
async def update_regulation(
    regulation_id: UUID,
    payload: RegulationUpdate,
    request: Request,
    current_user: User = Depends(require_permissions("regulations:manage")),
    db: AsyncSession = Depends(get_async_db),
) -> RegulationRead:
    regulation = await compliance_service.update_regulation(
        db,
        regulation_id,
        payload,
        actor=current_user,
        ip_address=request.client.host if request.client else None,
    )
    return RegulationRead.model_validate(regulation)
