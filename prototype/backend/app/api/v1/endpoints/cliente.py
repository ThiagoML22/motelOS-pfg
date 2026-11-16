"""El cliente en su habitación (migraciones 013 y 020): sin sesión.

Entra de dos maneras: con el enlace firmado del ticket, que solo abre su turno, o con el QR fijo de la habitación, que
vincula su celular a la estadía (app/services/qr_habitacion.py). En ese caso el enlace sirve solo en el celular
vinculado y mientras el vínculo siga vigente. Un enlace inválido, de un motel suspendido o de un turno que no existe
responde siempre lo mismo.
"""

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.calificacion import LARGO_RESENA, TODOS_LOS_PROBLEMAS
from app.models.turno import Turno
from app.models.vinculo_cliente import VinculoCliente
from app.services import acceso_cliente, qr_habitacion
from app.services.equipos import huella_de

router = APIRouter()

NO_VALIDO = qr_habitacion.NO_VALIDO


def _no_valido() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NO_VALIDO)


async def _vinculo_del_enlace(db: AsyncSession, request: Request, token: str) -> tuple[VinculoCliente, Turno]:
    datos = qr_habitacion.leer_token_de_vinculo(token)
    await qr_habitacion.establecimiento_activo(db, datos[0] if datos else None)
    vigente = await qr_habitacion.vinculo_vigente(db, datos[1], qr_habitacion.marca_de(request))
    if vigente is None:
        raise _no_valido()
    return vigente


async def turno_del_enlace(
    request: Request, token: str = Path(max_length=120), db: AsyncSession = Depends(get_db)
) -> Turno:
    if qr_habitacion.es_de_vinculo(token):
        return (await _vinculo_del_enlace(db, request, token))[1]
    datos = acceso_cliente.leer_token(token)
    await qr_habitacion.establecimiento_activo(db, datos[0] if datos else None)
    turno = (await db.execute(select(Turno).where(Turno.id == datos[1]))).scalars().first()
    if turno is None:
        raise _no_valido()
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
    # Opcional: hasta seis palabras, que pasan por el filtro de app/services/moderacion.py.
    resena: str | None = Field(default=None, max_length=LARGO_RESENA)


# --- El QR fijo de la habitación (migración 020) ---------------------------------------------------------------------
# POST y no GET: la vista previa de un enlace (la de un chat, por ejemplo) no vincula a nadie.


def _marca(request: Request, response: Response) -> str:
    marca = qr_habitacion.marca_de(request) or qr_habitacion.nueva_marca()
    qr_habitacion.poner_cookie(response, marca)
    return marca


@router.post("/habitacion/{qr}/entrar")
async def entrar(
    request: Request, response: Response, qr: str = Path(max_length=120), db: AsyncSession = Depends(get_db)
) -> dict:
    establecimiento, habitacion = await qr_habitacion.habitacion_del_qr(db, qr)
    marca = _marca(request, response)
    return await qr_habitacion.entrar(db, establecimiento, habitacion, huella_de(marca))


@router.post("/habitacion/{qr}/aviso")
async def avisar(qr: str = Path(max_length=120), db: AsyncSession = Depends(get_db)) -> dict:
    _, habitacion = await qr_habitacion.habitacion_del_qr(db, qr)
    return await qr_habitacion.avisar(db, habitacion)


@router.post("/sumar/{invitacion}")
async def sumar(
    request: Request, response: Response, invitacion: str = Path(max_length=120), db: AsyncSession = Depends(get_db)
) -> dict:
    marca = _marca(request, response)
    return await qr_habitacion.sumar(db, invitacion, huella_de(marca))


@router.post("/{token}/invitacion")
async def invitar(request: Request, token: str = Path(max_length=120), db: AsyncSession = Depends(get_db)) -> dict:
    """Solo desde un celular vinculado con el QR fijo: el enlace del ticket no suma celulares."""
    if not qr_habitacion.es_de_vinculo(token):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Con el ticket no se suman celulares.")
    vinculo, turno = await _vinculo_del_enlace(db, request, token)
    return await qr_habitacion.invitar(db, vinculo, turno)


# --- La estadía ------------------------------------------------------------------------------------------------------


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
    return await acceso_cliente.calificar(db, turno, datos.puntaje, datos.problemas, datos.resena)
