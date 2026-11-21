from backend.routers.audit import router as audit_router
from backend.routers.auth import router as auth_router
from backend.routers.catalogs import router as catalogs_router
from backend.routers.certifications import router as certifications_router
from backend.routers.regulations import router as regulations_router
from backend.routers.requests import router as requests_router
from backend.routers.roles import router as roles_router
from backend.routers.routes import router as routes_router
from backend.routers.users import router as users_router

__all__ = [
    "auth_router",
    "users_router",
    "roles_router",
    "catalogs_router",
    "routes_router",
    "regulations_router",
    "requests_router",
    "certifications_router",
    "audit_router",
]
