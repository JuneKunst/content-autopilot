"""Database configuration and session management."""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import AsyncSession as AsyncSessionType
from sqlalchemy.orm import DeclarativeBase, asyncsessionmaker

from content_autopilot.config import settings


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


# Create async engine
async_engine = create_async_engine(
    settings.db_url,
    echo=False,
    future=True,
    pool_pre_ping=True,
)

# Create async session factory
async_session = asyncsessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSessionType, None]:
    """Dependency injection for FastAPI to get async session."""
    async with async_session() as session:
        yield session
