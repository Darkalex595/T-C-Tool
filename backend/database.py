from __future__ import annotations

from collections.abc import AsyncGenerator, Generator

from sqlalchemy import MetaData, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config import (
    build_async_engine_config,
    build_sync_engine_config,
    settings,
)

# Convención explícita de nombres en PostgreSQL para migraciones limpias con Alembic
POSTGRES_INDEXES_NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

ASYNC_DATABASE_URL, ASYNC_CONNECT_ARGS = build_async_engine_config()
SYNC_DATABASE_URL, SYNC_CONNECT_ARGS = build_sync_engine_config()


class Base(DeclarativeBase):
    """Clase base declarativa para todos los modelos ORM de PostgreSQL."""

    metadata = MetaData(naming_convention=POSTGRES_INDEXES_NAMING_CONVENTION)


async_engine: AsyncEngine = create_async_engine(
    ASYNC_DATABASE_URL,
    echo=settings.SQL_ECHO,
    connect_args=ASYNC_CONNECT_ARGS,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=300,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

sync_engine = create_engine(
    SYNC_DATABASE_URL,
    echo=settings.SQL_ECHO,
    connect_args=SYNC_CONNECT_ARGS,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=300,
)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    class_=Session,
    expire_on_commit=False,
    autoflush=False,
)


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependencia FastAPI para sesiones asíncronas con asyncpg."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_sync_db() -> Generator[Session, None, None]:
    """Dependencia opcional para jobs síncronos, CLI o migraciones."""
    with SyncSessionLocal() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
