from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "Motel C.C. API"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/motel_db"
    SQL_ECHO: bool = False
    CORS_ORIGINS: str = "http://localhost:5173"


settings = Settings()
