"""Async Engine 与 Session Factory。"""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from nexusmcp.infrastructure.persistence.models import ALL_MODELS

# Runtime 与 Alembic 必须注册同一组 Table；否则首个跨模块 Flush 无法解析尚未导入的 Foreign Key。
_ = ALL_MODELS


def create_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    """创建 SQLAlchemy Async Engine；调用方负责在 Lifespan 中释放。"""

    if not database_url.startswith("postgresql+asyncpg://"):
        raise ValueError("database URL must use postgresql+asyncpg")
    return create_async_engine(
        database_url,
        echo=echo,
        pool_pre_ping=True,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """创建不在 Repository 内自动 Commit 的 Async Session Factory。"""

    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
