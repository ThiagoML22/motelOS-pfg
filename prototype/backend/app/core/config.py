from decimal import Decimal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Valor de desarrollo: sirve para levantar el prototipo en una máquina local y se rechaza en producción.
JWT_SECRET_DESARROLLO = "solo-para-desarrollo-local-no-usar-en-produccion"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "Motel C.C. API"
    ENTORNO: str = "desarrollo"  # desarrollo | produccion
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/motel_db"
    SQL_ECHO: bool = False
    CORS_ORIGINS: str = "http://localhost:5173"
    # RNF-08: la patente se elimina dentro de las N horas posteriores al cierre del turno (24 h, aprobado por
    # la gerencia el 06/10/2026) y la tarea de depuración corre cada DEPURACION_INTERVALO_MIN minutos.
    RETENCION_PATENTE_HORAS: int = 24
    DEPURACION_INTERVALO_MIN: int = 60

    # RNF-04: sesión con JWT en una cookie httpOnly. La sesión dura una guardia de 8 h más 1 h de margen.
    JWT_SECRET: str = JWT_SECRET_DESARROLLO
    JWT_ALGORITMO: str = "HS256"
    SESION_HORAS: int = 9
    COOKIE_NOMBRE: str = "motelos_sesion"
    COOKIE_SECURE: bool = False  # True en producción (HTTPS)
    # Bloqueo por intentos fallidos de inicio de sesión.
    LOGIN_MAX_INTENTOS: int = 5
    LOGIN_BLOQUEO_MIN: int = 15
    # Costo de argon2id para las claves (valores por defecto de argon2-cffi; las pruebas los bajan).
    ARGON2_TIME_COST: int = 3
    ARGON2_MEMORY_KIB: int = 65536

    # Guardias (RF-08): franjas de 06:00, 14:00 y 22:00 en la hora local del motel. Una guardia abierta hasta
    # GUARDIA_ANTICIPACION_MIN minutos antes de su hora de inicio corresponde a esa franja.
    ZONA_HORARIA: str = "America/Argentina/Buenos_Aires"
    GUARDIA_ANTICIPACION_MIN: int = 120
    # Fondo de cambio que recibe cada guardia en la gaveta: $25.000, aprobado por la gerencia en el acta de
    # validación del 19/10/2026 (punto 5). Se suma al efectivo que el sistema espera en el arqueo.
    FONDO_INICIAL_CAJA: Decimal = Decimal("25000")

    @model_validator(mode="after")
    def exigir_configuracion_segura(self) -> "Settings":
        if self.ENTORNO == "produccion":
            if self.JWT_SECRET == JWT_SECRET_DESARROLLO or len(self.JWT_SECRET) < 32:
                raise ValueError("En producción JWT_SECRET debe ser una clave propia de al menos 32 caracteres.")
            if not self.COOKIE_SECURE:
                raise ValueError("En producción la cookie de sesión debe viajar solo por HTTPS (COOKIE_SECURE=True).")
        return self


settings = Settings()
