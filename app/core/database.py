"""
محرك قاعدة البيانات وإدارة الجلسات — SQLAlchemy Async
"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """الكلاس الأساسي لجميع الـ Models"""
    pass


async def get_db() -> AsyncSession:
    """مولّد جلسة قاعدة البيانات — يُستخدم كـ Dependency في FastAPI"""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """إنشاء الجداول عند بدء التطبيق (للتطوير فقط)"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
