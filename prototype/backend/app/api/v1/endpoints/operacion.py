"""Operación diaria (migración 016): arreglos, ropa y lo que ve la gerencia.

`router` lo usa todo el personal con sesión. `gerencia` se monta solo para el rol ADMINISTRADOR (main.py).
"""

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import operador_actual
from app.core.database import get_db
from app.models.operador import Operador
from app.schemas.configuracion import TOPE_IMPORTE
from app.services import arreglos, ropa, traspasos

router = APIRouter()
gerencia = APIRouter()

Rubro = Literal["AIRE", "PLOMERIA", "ELECTRICIDAD", "TV", "MUEBLES", "OTRO"]
Prenda = Literal["TOALLAS", "SABANAS"]


def _con_texto(valor: str) -> str:
    if not valor.strip():
        raise ValueError("Este dato no puede quedar vacío.")
    return valor


class ArregloAlta(BaseModel):
    habitacion_id: int
    tipo: Literal["FALLA", "MANTENIMIENTO"] = "FALLA"
    rubro: Rubro
    descripcion: str = Field(min_length=1, max_length=200)
    fuera_de_servicio: bool = False

    _descripcion = field_validator("descripcion")(_con_texto)


class ArregloResuelto(BaseModel):
    reparado_por: str = Field(min_length=1, max_length=80)
    trabajo: str | None = Field(default=None, max_length=200)
    costo: float | None = Field(default=None, ge=0, le=TOPE_IMPORTE)
    habilitar: bool = True

    _reparado = field_validator("reparado_por")(_con_texto)


class CostoArreglo(BaseModel):
    costo: float | None = Field(default=None, ge=0, le=TOPE_IMPORTE)


class MovimientoRopa(BaseModel):
    prenda: Prenda
    tipo: Literal["LAVANDERIA_SALE", "LAVANDERIA_VUELVE", "COMPRA", "BAJA"]
    cantidad: int = Field(ge=1, le=100000)


@router.get("/arreglos")
async def listar_arreglos(
    habitacion_id: int | None = None,
    sin_resolver: bool = False,
    db: AsyncSession = Depends(get_db),
    operador: Operador = Depends(operador_actual),
) -> list[dict]:
    return await arreglos.listar(db, operador, habitacion_id, sin_resolver)


@router.post("/arreglos", status_code=201)
async def reportar_arreglo(
    datos: ArregloAlta, db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)
) -> dict:
    return await arreglos.reportar(
        db, operador, datos.habitacion_id, datos.tipo, datos.rubro, datos.descripcion, datos.fuera_de_servicio
    )


@router.post("/arreglos/{arreglo_id}/empezar")
async def empezar_arreglo(
    arreglo_id: int, db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)
) -> dict:
    return await arreglos.empezar(db, operador, arreglo_id)


@router.post("/arreglos/{arreglo_id}/resolver")
async def resolver_arreglo(
    arreglo_id: int,
    datos: ArregloResuelto,
    db: AsyncSession = Depends(get_db),
    operador: Operador = Depends(operador_actual),
) -> dict:
    return await arreglos.resolver(
        db, operador, arreglo_id, datos.reparado_por, datos.trabajo, datos.costo, datos.habilitar
    )


@router.post("/ropa/movimientos", status_code=201)
async def movimiento_de_ropa(
    datos: MovimientoRopa, db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)
) -> dict:
    return await ropa.registrar_movimiento(db, operador, datos.prenda, datos.tipo, datos.cantidad)


# --- Solo la gerencia ------------------------------------------------------------------------------------------------
@gerencia.get("/tablero")
async def tablero(db: AsyncSession = Depends(get_db)) -> dict:
    return {
        "arreglos": await arreglos.tablero(db),
        "ropa": await ropa.historial(db),
        "traspasos": await traspasos.historial(db),
        "traslados": await arreglos.traslados(db),
    }


@gerencia.patch("/arreglos/{arreglo_id}/costo")
async def costo_del_arreglo(
    arreglo_id: int,
    datos: CostoArreglo,
    db: AsyncSession = Depends(get_db),
    operador: Operador = Depends(operador_actual),
) -> dict:
    return await arreglos.cargar_costo(db, operador, arreglo_id, datos.costo)
