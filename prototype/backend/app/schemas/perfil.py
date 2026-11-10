from datetime import datetime

from pydantic import BaseModel, Field

from app.core.seguridad import LARGO_MINIMO_CLAVE


class PerfilResponse(BaseModel):
    id: int
    usuario: str
    nombre_visible: str
    rol: str
    establecimiento_nombre: str | None = None
    establecimiento_codigo: str | None = None
    creado_en: datetime
    ultimo_acceso: datetime | None = None
    # Actividad de los últimos 30 días (para la gerencia, en general cero: no abre guardias).
    guardias_30_dias: int = 0
    turnos_30_dias: int = 0
    arqueos_30_dias: int = 0


class PerfilCambio(BaseModel):
    nombre_visible: str = Field(min_length=1, max_length=60)


class ClavePropia(BaseModel):
    actual: str = Field(min_length=1, max_length=128)
    nueva: str = Field(min_length=LARGO_MINIMO_CLAVE, max_length=128)


class ClaveRestablecida(BaseModel):
    nueva: str = Field(min_length=LARGO_MINIMO_CLAVE, max_length=128)
