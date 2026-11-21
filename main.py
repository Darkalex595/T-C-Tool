from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_sanitized_target, settings
from backend.database import async_engine, get_async_db
from backend.routers import (
    audit_router,
    auth_router,
    catalogs_router,
    certifications_router,
    regulations_router,
    requests_router,
    roles_router,
    routes_router,
    users_router,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Ciclo de vida de la aplicación: libera conexiones del pool al apagar el servidor."""
    yield
    await async_engine.dispose()


app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description="API de Cumplimiento Comercial Multinacional y Rutas Logísticas.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for api_router in (
    auth_router,
    users_router,
    roles_router,
    catalogs_router,
    routes_router,
    regulations_router,
    requests_router,
    certifications_router,
    audit_router,
):
    app.include_router(api_router, prefix=settings.API_PREFIX)


@app.get("/", tags=["System"])
async def root() -> dict[str, str]:
    """Información básica de entrada de la API."""
    return {
        "service": settings.API_TITLE,
        "version": settings.API_VERSION,
        "environment": settings.APP_ENV,
        "docs": "/docs",
    }


@app.get("/health", tags=["System"])
async def health_check(db: AsyncSession = Depends(get_async_db)) -> dict[str, Any]:
    """Verifica que FastAPI esté activo y pueda consultar PostgreSQL en tiempo real."""
    try:
        result = await db.execute(
            text(
                "SELECT current_database(), "
                "(SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public')"
            )
        )
        db_name, table_count = result.one()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"No se pudo conectar con PostgreSQL: {exc}",
        ) from exc

    return {
        "status": "ok",
        "database": "connected",
        "database_name": db_name,
        "public_tables": table_count,
        "target": get_sanitized_target(),
    }
