from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = "postgresql+asyncpg://neondb_owner:npg_gfRjZX9vsPk1@ep-round-hall-ayrk6oi7-pooler.c-5.us-east-2.aws.neon.tech/neondb?ssl=require"

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


class Base(AsyncAttrs, DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session