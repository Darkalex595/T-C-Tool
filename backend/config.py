from __future__ import annotations

import ssl
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "db", "postgres"}
_SSL_REQUIRE_MODES = {"require", "verify-ca", "verify-full"}


class DatabaseSettings(BaseSettings):
    """Configuración unificada para PostgreSQL en local (Docker/nativo) y en la nube."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_ENV: Literal["development", "staging", "production"] = "development"
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/trade_compliance"
    )
    SYNC_DATABASE_URL: str | None = Field(default=None)
    DB_SSL: Literal["auto", "require", "disable"] = "auto"
    DB_SSL_VERIFY: bool = False
    DB_SSL_CA_FILE: str | None = None
    DB_USE_POOLER: bool | None = None
    SQL_ECHO: bool = False

    # Configuración general de la API FastAPI
    API_TITLE: str = "GlobalTrade Compliance API"
    API_VERSION: str = "0.1.0"
    API_PREFIX: str = "/api/v1"
    CORS_ORIGINS: list[str] = Field(
        default=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
        ]
    )

    # Configuración de Seguridad y JWT (Paso 2)
    JWT_SECRET_KEY: str = Field(
        default="dev-only-insecure-secret-change-in-env-min-32-chars"
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60


settings = DatabaseSettings()


def _normalize_scheme(scheme: str, target_driver: str) -> str:
    base = scheme.split("+")[0].lower()
    if base in {"postgres", "postgresql"}:
        return f"postgresql+{target_driver}"
    return scheme


def _should_use_ssl(hostname: str | None, query_params: dict[str, str]) -> bool:
    if settings.DB_SSL == "require":
        return True
    if settings.DB_SSL == "disable":
        return False

    sslmode = query_params.get("sslmode", "").lower()
    ssl_param = query_params.get("ssl", "").lower()
    if sslmode in _SSL_REQUIRE_MODES or ssl_param in {"true", "1", "require"}:
        return True
    if sslmode == "disable" or ssl_param in {"false", "0", "disable"}:
        return False

    host = (hostname or "").lower()
    if not host or host in _LOCAL_HOSTS or host.endswith(".local"):
        return False
    return True


def _is_pooler_endpoint(hostname: str | None, port: int | None) -> bool:
    if settings.DB_USE_POOLER is not None:
        return settings.DB_USE_POOLER
    host = (hostname or "").lower()
    return "-pooler" in host or port == 6543


def build_async_engine_config() -> tuple[str, dict[str, Any]]:
    """Prepara URL para asyncpg y traduce sslmode/pooler a connect_args válidos."""
    parts = urlsplit(settings.DATABASE_URL.strip())
    raw_query = dict(parse_qsl(parts.query, keep_blank_values=True))

    use_ssl = _should_use_ssl(parts.hostname, raw_query)
    use_pooler = _is_pooler_endpoint(parts.hostname, parts.port)

    # asyncpg falla si la URL incluye sslmode o channel_binding en la query string
    cleaned_query = {
        k: v
        for k, v in raw_query.items()
        if k.lower() not in {"sslmode", "ssl", "channel_binding"}
    }

    async_url = urlunsplit(
        (
            _normalize_scheme(parts.scheme, "asyncpg"),
            parts.netloc,
            parts.path,
            urlencode(cleaned_query),
            parts.fragment,
        )
    )

    connect_args: dict[str, Any] = {}
    if use_ssl:
        sslmode = raw_query.get("sslmode", "").lower()
        if settings.DB_SSL_CA_FILE:
            connect_args["ssl"] = ssl.create_default_context(cafile=settings.DB_SSL_CA_FILE)
        elif settings.DB_SSL_VERIFY or sslmode in {"verify-ca", "verify-full"}:
            connect_args["ssl"] = ssl.create_default_context()
        else:
            # Equivalente a sslmode=require en psycopg2: cifra con TLS sin fallar con la CA interna de Supabase
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            connect_args["ssl"] = ssl_ctx
    if use_pooler:
        # Evita errores DuplicatePreparedStatementError detrás de PgBouncer (Neon/Supabase)
        connect_args["statement_cache_size"] = 0

    return async_url, connect_args


def build_sync_engine_config() -> tuple[str, dict[str, Any]]:
    """Prepara URL para psycopg2 / Alembic a partir de SYNC_DATABASE_URL o DATABASE_URL."""
    source_url = (settings.SYNC_DATABASE_URL or settings.DATABASE_URL).strip()
    parts = urlsplit(source_url)
    raw_query = dict(parse_qsl(parts.query, keep_blank_values=True))

    use_ssl = _should_use_ssl(parts.hostname, raw_query)

    cleaned_query = {
        k: v
        for k, v in raw_query.items()
        if k.lower() not in {"ssl", "channel_binding"}
    }
    if use_ssl and "sslmode" not in {k.lower() for k in cleaned_query}:
        cleaned_query["sslmode"] = "require"
    elif not use_ssl:
        cleaned_query = {k: v for k, v in cleaned_query.items() if k.lower() != "sslmode"}

    sync_url = urlunsplit(
        (
            _normalize_scheme(parts.scheme, "psycopg2"),
            parts.netloc,
            parts.path,
            urlencode(cleaned_query),
            parts.fragment,
        )
    )
    return sync_url, {}


def get_sanitized_target() -> dict[str, Any]:
    """Devuelve información no sensible de la conexión activa para logs y diagnósticos."""
    parts = urlsplit(settings.DATABASE_URL.strip())
    raw_query = dict(parse_qsl(parts.query, keep_blank_values=True))
    return {
        "host": parts.hostname or "localhost",
        "port": parts.port or 5432,
        "database": parts.path.lstrip("/") or "trade_compliance",
        "ssl_enabled": _should_use_ssl(parts.hostname, raw_query),
        "pooler_mode": _is_pooler_endpoint(parts.hostname, parts.port),
    }
