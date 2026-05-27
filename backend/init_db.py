import asyncio

from sqlalchemy import text

from app.db.base import Base
from app.db.session import engine

# Import model classes so SQLAlchemy registers every table on Base.metadata.
from app.models import DAGTaskNode, ExperienceLedger, IdentityGraph, Project  # noqa: F401


async def init_db() -> None:
    """Create PostgreSQL extensions and all PAOS core database tables."""

    async with engine.begin() as conn:
        # pgvector is required before creating columns that use Vector(1536).
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)


if __name__ == "__main__":
    asyncio.run(init_db())
