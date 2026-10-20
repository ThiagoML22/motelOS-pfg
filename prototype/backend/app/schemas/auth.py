from pydantic import BaseModel, ConfigDict, Field

from app.schemas.caja import GuardiaPublica


class LoginRequest(BaseModel):
    usuario: str = Field(min_length=1, max_length=40)
    clave: str = Field(min_length=1, max_length=128)


class OperadorPublico(BaseModel):
    """Lo que se muestra de un operador: nunca el hash de la clave ni los datos de bloqueo."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    usuario: str
    nombre_visible: str
    rol: str


class SesionResponse(BaseModel):
    operador: OperadorPublico
    # La guardia abierta en la ventanilla, si hay una (sin importes).
    guardia: GuardiaPublica | None = None
