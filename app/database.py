from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker
)
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

# Create connection to database
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    echo=settings.DEBUG,
)

SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

class Base(DeclarativeBase):
    pass

# Runs before every API request
async def get_db():
    async with SessionLocal() as session:
        yield session