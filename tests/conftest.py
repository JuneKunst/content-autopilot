import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker


@pytest.fixture
async def async_engine():
    """Create an async SQLAlchemy engine for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    yield engine
    await engine.dispose()


@pytest.fixture
async def async_session_factory(async_engine):
    """Create an async session factory for testing."""
    async_session = sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return async_session


@pytest.fixture
async def async_session(async_session_factory):
    """Create an async session for testing."""
    async with async_session_factory() as session:
        yield session
