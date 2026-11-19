from __future__ import annotations

import asyncio

from sqlalchemy import text

from backend.config import get_sanitized_target
from backend.database import async_engine


async def check_connection() -> None:
    """Verifica conectividad con PostgreSQL (local o nube) sin exponer credenciales."""
    target = get_sanitized_target()
    print(
        f"Conectando a {target['host']}:{target['port']}/{target['database']} "
        f"(ssl={target['ssl_enabled']}, pooler={target['pooler_mode']})..."
    )

    async with async_engine.connect() as conn:
        info = await conn.execute(
            text("SELECT version(), current_database(), current_user")
        )
        version, db_name, db_user = info.one()

        tables_res = await conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' ORDER BY tablename"
            )
        )
        tables = [row[0] for row in tables_res.all()]

    await async_engine.dispose()

    print(f"Conexión exitosa -> BD: {db_name} | Usuario: {db_user}")
    print(f"Motor: {version.split(',')[0]}")
    print(f"Tablas en public ({len(tables)}): {', '.join(tables) if tables else 'Ninguna aún'}")


if __name__ == "__main__":
    asyncio.run(check_connection())
