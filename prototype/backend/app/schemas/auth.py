from pydantic import BaseModel, ConfigDict, Field

from app.schemas.caja import GuardiaPublica


class LoginRequest(BaseModel):
    # Código del establecimiento (multiinquilino). Vacío: el predeterminado de la instalación; "plataforma": el
    # equipo que da de alta establecimientos.
    establecimiento: str | None = Field(default=None, max_length=30)
    usuario: str = Field(min_length=1, max_length=40)
    clave: str = Field(min_length=1, max_length=128)


class OperadorPublico(BaseModel):
    """Lo que se muestra de un operador: nunca el hash de la clave ni los datos de bloqueo."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    usuario: str
    nombre_visible: str
    rol: str


class EstablecimientoPublico(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    codigo: str
    nombre: str


class SesionResponse(BaseModel):
    operador: OperadorPublico
    # El establecimiento de la sesión; nulo para la plataforma.
    establecimiento: EstablecimientoPublico | None = None
    # La guardia abierta en la ventanilla, si hay una (sin importes).
    guardia: GuardiaPublica | None = None
