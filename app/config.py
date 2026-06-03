from pydantic_settings import BaseSettings
from typing import List, Optional
from pydantic import model_validator

class Settings(BaseSettings):
    # Database Configuration
    POSTGRES_USER: str = "appuser"
    POSTGRES_PASSWORD: str = "StrongPass123"
    POSTGRES_DB: str = "appdb"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    
    # Redis Configuration
    REDIS_PASSWORD: str = "RedisPass123"
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    # Connection Strings (if provided directly, they will take precedence)
    DATABASE_URL: Optional[str] = None
    REDIS_URL: Optional[str] = None
    
    # Security
    SECRET_KEY: str = "change-me-in-production"
    ALLOWED_ORIGINS: List[str] = ["*"]
    
    # App
    DEBUG: bool = False
    APP_NAME: str = "Production API"

    @model_validator(mode="before")
    @classmethod
    def parse_allowed_origins(cls, data: any) -> any:
        if isinstance(data, dict):
            origins = data.get("ALLOWED_ORIGINS")
            if isinstance(origins, str):
                if origins.strip().startswith("[") and origins.strip().endswith("]"):
                    import json
                    try:
                        data["ALLOWED_ORIGINS"] = json.loads(origins)
                    except Exception:
                        pass
                else:
                    data["ALLOWED_ORIGINS"] = [o.strip() for o in origins.split(",") if o.strip()]
        return data

    @model_validator(mode="after")
    def assemble_urls(self) -> 'Settings':
        if not self.DATABASE_URL:
            self.DATABASE_URL = f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        if not self.REDIS_URL:
            self.REDIS_URL = f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return self

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()