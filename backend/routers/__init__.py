from backend.routers.auth import router as auth_router
from backend.routers.catalogs import router as catalogs_router
from backend.routers.certifications import router as certifications_router
from backend.routers.regulations import router as regulations_router
from backend.routers.requests import router as requests_router
from backend.routers.routes import router as routes_router

__all__ = [
    "auth_router",
    "catalogs_router",
    "routes_router",
    "regulations_router",
    "requests_router",
    "certifications_router",
]
