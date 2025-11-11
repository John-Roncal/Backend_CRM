import os
from pydantic_settings import BaseSettings
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, DeclarativeBase

class Settings(BaseSettings):
    DATABASE_URL: str
    GOOGLE_API_KEY: str

    class Config:
        env_file = ".env"

settings = Settings()

# Configurar el motor asíncrono de SQLAlchemy
engine = create_async_engine(settings.DATABASE_URL)

# Base para los modelos declarativos
class Base(DeclarativeBase):
    pass

# Fábrica de sesiones asíncronas
AsyncSessionFactory = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Dependencia de FastAPI para obtener la sesión de BD
async def get_db_session():
    async with AsyncSessionFactory() as session:
        yield session