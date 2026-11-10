"""Aislamiento por establecimiento (multiinquilino, migración 006).

El establecimiento de una sesión de base de datos vive en `session.info["establecimiento_id"]` y sale del token
firmado (deps.operador_actual) o del código que se indica al iniciar sesión (auth.login), nunca del cuerpo de
una petición. Con ese valor:

1. Cada consulta del ORM sobre un modelo `DeEstablecimiento` recibe el filtro `establecimiento_id = valor`
   (evento do_orm_execute). Es la capa que también corre en las pruebas con SQLite.
2. Cada objeto nuevo toma el establecimiento de la sesión antes de guardarse (evento before_flush).
3. En PostgreSQL, cada transacción fija `app.establecimiento_id` (evento after_begin), que usan las políticas
   de Row Level Security. Si una consulta olvidara el filtro, la base igual no devuelve filas de otro
   establecimiento; y si la transacción no fija el valor, motel_app no ve ninguna fila.

El valor 0 (PLATAFORMA) identifica a la plataforma, que da de alta establecimientos y no ve su operación.
Sin valor en la sesión no se agrega filtro: es el caso de los scripts del dueño de las tablas y de la carga de
datos de las pruebas. La aplicación siempre fija el valor antes de consultar.
"""

from sqlalchemy import Column, ForeignKey, Integer, event, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, declared_attr, with_loader_criteria

CLAVE = "establecimiento_id"
PLATAFORMA = 0
# Opción de ejecución para las pocas consultas que recorren todos los establecimientos (resumen de la
# plataforma en SQLite y depuración de patentes). En PostgreSQL esas consultas las resuelve la base.
SIN_FILTRO = "sin_filtro_de_establecimiento"


class DeEstablecimiento:
    """Mezcla para los modelos cuyas filas pertenecen a un establecimiento."""

    @declared_attr
    def establecimiento_id(cls):  # noqa: N805
        return Column(Integer, ForeignKey("establecimientos.id"), nullable=False, index=True)


def establecimiento_de(db: AsyncSession | Session) -> int | None:
    return db.info.get(CLAVE)


async def fijar_establecimiento(db: AsyncSession, establecimiento_id: int) -> None:
    """Asocia la sesión a un establecimiento; en PostgreSQL también la transacción en curso."""
    db.info[CLAVE] = establecimiento_id
    if db.get_bind().dialect.name == "postgresql":
        await db.execute(
            text("SELECT set_config('app.establecimiento_id', :valor, true)"), {"valor": str(establecimiento_id)}
        )


@event.listens_for(Session, "after_begin")
def _fijar_en_la_transaccion(session: Session, _transaction, connection) -> None:
    establecimiento_id = session.info.get(CLAVE)
    if establecimiento_id is not None and connection.dialect.name == "postgresql":
        # El tercer argumento (true) limita el valor a la transacción: la conexión vuelve limpia al pool.
        connection.execute(
            text("SELECT set_config('app.establecimiento_id', :valor, true)"), {"valor": str(establecimiento_id)}
        )


@event.listens_for(Session, "do_orm_execute")
def _filtrar_por_establecimiento(estado) -> None:
    establecimiento_id = estado.session.info.get(CLAVE)
    if (
        establecimiento_id is None
        or estado.is_column_load
        or estado.is_relationship_load
        or estado.execution_options.get(SIN_FILTRO, False)
        or not (estado.is_select or estado.is_update or estado.is_delete)
    ):
        return
    if establecimiento_id == PLATAFORMA:
        criterio = with_loader_criteria(
            DeEstablecimiento, lambda cls: cls.establecimiento_id.is_(None), include_aliases=True
        )
    else:
        criterio = with_loader_criteria(
            DeEstablecimiento, lambda cls: cls.establecimiento_id == establecimiento_id, include_aliases=True
        )
    estado.statement = estado.statement.options(criterio)


@event.listens_for(Session, "before_flush")
def _completar_establecimiento(session: Session, _flush_context, _instances) -> None:
    establecimiento_id = session.info.get(CLAVE)
    if not establecimiento_id:  # sin valor o la plataforma: el objeto debe traer el suyo
        return
    for objeto in session.new:
        if isinstance(objeto, DeEstablecimiento) and objeto.establecimiento_id is None:
            objeto.establecimiento_id = establecimiento_id
