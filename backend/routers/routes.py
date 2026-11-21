from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_db
from backend.models import LogisticsRouteCode, ProductClassification, User
from backend.schemas.compliance import (
    ImportRouteCreate,
    ImportRouteRead,
    ImportRouteUpdate,
)
from backend.security import get_current_user, require_permissions
from backend.services import compliance as compliance_service

router = APIRouter(prefix="/routes", tags=["Logistics Routes"])


@router.get("", response_model=list[ImportRouteRead])
async def list_routes(
    country_code: str | None = Query(default=None, min_length=2, max_length=2),
    classification: ProductClassification | None = Query(default=None),
    route_code: LogisticsRouteCode | None = Query(default=None),
    search: str | None = Query(default=None, max_length=120),
    active_only: bool = Query(default=True),
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> list[ImportRouteRead]:
    """Lista rutas logísticas activas (filtrables por país, clasificación, tipo de ruta y texto)."""
    routes = await compliance_service.list_import_routes(
        db,
        country_code=country_code,
        classification=classification,
        route_code=route_code,
        search=search,
        active_only=active_only,
    )
    return [ImportRouteRead.model_validate(r) for r in routes]


@router.get("/{route_id}", response_model=ImportRouteRead)
async def get_route(
    route_id: UUID,
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
) -> ImportRouteRead:
    route = await compliance_service.get_import_route(db, route_id)
    return ImportRouteRead.model_validate(route)


@router.post(
    "",
    response_model=ImportRouteRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_route(
    payload: ImportRouteCreate,
    request: Request,
    current_user: User = Depends(require_permissions("routes:manage")),
    db: AsyncSession = Depends(get_async_db),
) -> ImportRouteRead:
    route = await compliance_service.create_import_route(
        db,
        payload,
        actor=current_user,
        ip_address=request.client.host if request.client else None,
    )
    return ImportRouteRead.model_validate(route)


@router.patch("/{route_id}", response_model=ImportRouteRead)
async def update_route(
    route_id: UUID,
    payload: ImportRouteUpdate,
    request: Request,
    current_user: User = Depends(require_permissions("routes:manage")),
    db: AsyncSession = Depends(get_async_db),
) -> ImportRouteRead:
    route = await compliance_service.update_import_route(
        db,
        route_id,
        payload,
        actor=current_user,
        ip_address=request.client.host if request.client else None,
    )
    return ImportRouteRead.model_validate(route)


@router.delete("/{route_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_route(
    route_id: UUID,
    request: Request,
    current_user: User = Depends(require_permissions("routes:manage")),
    db: AsyncSession = Depends(get_async_db),
) -> Response:
    """Elimina una ruta logística sin solicitudes asociadas (409 si está referenciada)."""
    await compliance_service.delete_import_route(
        db,
        route_id,
        actor=current_user,
        ip_address=request.client.host if request.client else None,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
