from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "Motel C.C. API"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/motel_db"
    SQL_ECHO: bool = False
    CORS_ORIGINS: str = "http://localhost:5173"
    # RNF-08: la patente se elimina dentro de las N horas posteriores al cierre del turno (plazo a acordar
    # con la gerencia: propuesta de 24 h) y la tarea de depuración corre cada DEPURACION_INTERVALO_MIN minutos.
    RETENCION_PATENTE_HORAS: int = 24
    DEPURACION_INTERVALO_MIN: int = 60


settings = Settings()
