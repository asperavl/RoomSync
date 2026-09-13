import uuid
import pytest
import pytest_asyncio
from typing import AsyncGenerator
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool
from sqlalchemy import text

from backend.app.config import settings
from backend.app.database import Base, get_db
from backend.app.main import app
from backend.app.models import User, Resource, Booking

# Test database URL - defaults to PostgreSQL test DB or configured DB
TEST_DATABASE_URL = settings.DATABASE_URL


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """Function-scoped engine using NullPool so asyncpg connections are bound strictly to the test loop."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False, future=True, poolclass=NullPool)
    async with engine.begin() as conn:
        if "postgresql" in TEST_DATABASE_URL:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist;"))
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provides an isolated AsyncSession for each test function."""
    async_session = async_sessionmaker(
        bind=test_engine,
        autoflush=False,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def sample_resource(db_session: AsyncSession) -> Resource:
    resource = Resource(
        name=f"Conference Room {uuid.uuid4().hex[:6]}",
        type="room",
        capacity=10,
        min_notice_minutes=30,
        cancellation_window_minutes=15,
    )
    db_session.add(resource)
    await db_session.commit()
    await db_session.refresh(resource)
    return resource


@pytest_asyncio.fixture(scope="function")
async def sample_user(db_session: AsyncSession) -> User:
    user = User(
        name="Alex Engineer",
        email=f"alex_{uuid.uuid4().hex[:8]}@company.internal",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user
