"""Async SQLAlchemy database engine and session factory."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import get_settings

settings = get_settings()


def _engine_kwargs() -> dict:
    """Bazaga qarab qo'shimcha sozlamalar.

    Supabase (va umuman pgbouncer turidagi ulanish poolerlari) —
    `transaction` rejimida ulanish har so'rovdan keyin boshqa mijozga
    berilishi mumkin. asyncpg esa **prepared statement** larni ulanishga
    bog'lab keshlaydi va keyingi so'rovda ular boshqa ulanishda topilmay
    `DuplicatePreparedStatementError` / `InvalidSQLStatementNameError`
    chiqadi. Bu xato tasodifiy ko'rinadi va tutish qiyin — yuk oshganda
    boshlanadi.

    Yechim: pooler bilan ishlaganda keshni o'chirish.
    Supabase'da bu 6543-port (`pooler.supabase.com`).
    """
    url = settings.async_database_url
    if not url.startswith("postgresql"):
        return {}

    kwargs: dict = {
        # Ulanish uzoq turib qolsa pooler uni yopadi; oldindan tekshiramiz.
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }
    if _uses_transaction_pooler(url):
        kwargs["connect_args"] = {"statement_cache_size": 0}
        kwargs["poolclass"] = NullPool
    return kwargs


def _uses_transaction_pooler(url: str) -> bool:
    """Ulanish pgbouncer-turidagi pooler orqalimi."""
    return ":6543" in url or "pgbouncer=true" in url


engine = create_async_engine(
    settings.async_database_url,
    echo=settings.debug,
    **_engine_kwargs(),
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session per request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
