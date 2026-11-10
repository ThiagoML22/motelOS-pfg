"""El cliente en su habitación (migración 013): sin sesión, con el enlace firmado del ticket.

El enlace es la única credencial y solo abre su turno. Un enlace inválido, de un motel suspendido o de un turno que no
existe responde siempre lo mismo.
"""

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.inquilino import fijar_establecimiento
from app.models.calificacion import TODOS_LOS_PROBLEMAS
from app.models.establecimiento import Establecimiento
from app.models.turno import Turno
from app.services import acceso_cliente

router = APIRouter()

NO_VALIDO = "Este código no es válido."


async def turno_del_enlace(token: str = Path(max_length=120), db: AsyncSession = Depends(get_db)) -> Turno:
    datos = acceso_cliente.leer_token(token)
    establecimiento = await db.get(Establecimiento, datos[0]) if datos else None
    if establecimiento is None or not establecimiento.activo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NO_VALIDO)
    await fijar_establecimiento(db, establecimiento.id)
    turno = (await db.execute(select(Turno).where(Turno.id == datos[1]))).scalars().first()
    if turno is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NO_VALIDO)
    return turno


class PedidoAlta(BaseModel):
    tipo: str
    articulo_id: int | None = None
    cantidad: int | None = None
    minutos: int | None = None
    medio_pago: str | None = None


class LineaCarrito(BaseModel):
    articulo_id: int
    cantidad: int = Field(ge=1, le=acceso_cliente.MAXIMA_CANTIDAD)


class CarritoAlta(BaseModel):
    lineas: list[LineaCarrito] = Field(min_length=1, max_length=acceso_cliente.MAXIMAS_LINEAS)


class CalificacionAlta(BaseModel):
    puntaje: int = Field(ge=1, le=5)
    problemas: int = Field(default=0, ge=0, le=TODOS_LOS_PROBLEMAS)


@router.get("/{token}")
async def estadia(turno: Turno = Depends(turno_del_enlace), db: AsyncSession = Depends(get_db)) -> dict:
    return await acceso_cliente.estadia(db, turno)


@router.post("/{token}/pedidos", status_code=status.HTTP_201_CREATED)
async def pedir(
    datos: PedidoAlta, turno: Turno = Depends(turno_del_enlace), db: AsyncSession = Depends(get_db)
) -> dict:
    return await acceso_cliente.pedir(
        db, turno, datos.tipo, datos.articulo_id, datos.cantidad, datos.minutos, datos.medio_pago
    )


@router.post("/{token}/carrito", status_code=status.HTTP_201_CREATED)
async def pedir_carrito(
    datos: CarritoAlta, turno: Turno = Depends(turno_del_enlace), db: AsyncSession = Depends(get_db)
) -> dict:
    return await acceso_cliente.pedir_carrito(db, turno, [(x.articulo_id, x.cantidad) for x in datos.lineas])


@router.post("/{token}/calificacion", status_code=status.HTTP_201_CREATED)
async def calificar(
    datos: CalificacionAlta, turno: Turno = Depends(turno_del_enlace), db: AsyncSession = Depends(get_db)
) -> dict:
    return await acceso_cliente.calificar(db, turno, datos.puntaje, datos.problemas)
