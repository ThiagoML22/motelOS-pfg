"""Escena de demostración: deja Motel C.C. casi lleno para mostrar la próxima libre y el registro de clientes perdidos.

Abre la guardia de conserje1 (si no hay ninguna) y ocupa las habitaciones libres con turnos que empezaron hace entre
10 minutos y casi 3 horas, dejando una en limpieza y las que se pidan disponibles. Las horas son pasadas y la aplicación
no las aceptaría: como cargar_historial, corre como dueño de las tablas y con session_replication_role = replica.

Uso (Docker): docker compose run --rm admin scripts.escena_lleno [disponibles]
"""

import asyncio
import random
import sys
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.inquilino import CLAVE
from app.models.establecimiento import Establecimiento
from app.models.evento_habitacion import COBRO, TURNO, EventoHabitacion
from app.models.guardia import Guardia
from app.models.habitacion import Habitacion
from app.models.operador import Operador
from app.models.tarifa import Tarifa
from app.models.turno import Turno
from scripts.cargar_historial import inicio_de_franja

CODIGO = "motelcc"
USUARIO = "conserje1"


async def llenar(disponibles: int) -> None:
    engine = create_async_engine(settings.DATABASE_URL)
    sesiones = async_sessionmaker(engine, expire_on_commit=False)
    rng = random.Random()
    ahora = datetime.now(UTC)
    try:
        async with sesiones() as db:
            establecimiento = (
                (await db.execute(select(Establecimiento).where(Establecimiento.codigo == CODIGO))).scalars().first()
            )
        if establecimiento is None:
            print(f"{CODIGO}: no existe.")
            return
        async with sesiones(info={CLAVE: establecimiento.id}) as db:
            await db.execute(text("SET LOCAL session_replication_role = replica"))
            conserje = (await db.execute(select(Operador).where(Operador.usuario == USUARIO))).scalars().first()
            guardia = (await db.execute(select(Guardia).where(Guardia.estado == "Abierta"))).scalars().first()
            if guardia is not None and guardia.operador_id != conserje.id:
                print("La guardia abierta es de otro conserje: cerrala antes de armar la escena.")
                return
            if guardia is None:
                inicio = inicio_de_franja(ahora, ZoneInfo(settings.ZONA_HORARIA))
                guardia = Guardia(
                    operador_id=conserje.id,
                    franja=f"{inicio.hour:02d}:00",
                    fondo_inicial=settings.FONDO_INICIAL_CAJA,
                    abierta_en=ahora - timedelta(hours=3),
                    estado="Abierta",
                )
                db.add(guardia)
                await db.flush()
            tarifas = {
                t.categoria_id: t for t in (await db.execute(select(Tarifa).where(Tarifa.vigente.is_(True)))).scalars()
            }
            libres = list(
                (
                    await db.execute(
                        select(Habitacion)
                        .where(Habitacion.activa.is_(True), Habitacion.estado == "Libre")
                        .order_by(Habitacion.numero)
                    )
                ).scalars()
            )
            a_ocupar = libres[: max(len(libres) - disponibles, 0)]
            for indice, habitacion in enumerate(a_ocupar):
                if indice == 0:
                    # La primera queda en limpieza: acaba de irse un cliente.
                    habitacion.estado = "En Limpieza"
                    db.add(
                        EventoHabitacion(
                            habitacion_id=habitacion.id,
                            estado_anterior="Ocupada",
                            estado_nuevo="En Limpieza",
                            origen=COBRO,
                            operador_id=conserje.id,
                            creado_en=ahora - timedelta(minutes=rng.randint(6, 14)),
                        )
                    )
                    continue
                tarifa = tarifas[habitacion.categoria_id]
                inicio_turno = ahora - timedelta(minutes=rng.randint(10, 170))
                turno = Turno(
                    habitacion_id=habitacion.id,
                    tarifa_id=tarifa.id,
                    tipo_cliente=rng.choice(("Auto", "Auto", "Moto", "Peaton")),
                    hora_inicio=inicio_turno,
                    estado="En Curso",
                    tarifa_base=tarifa.tarifa_base,
                    total_general=tarifa.tarifa_base,
                    operador_apertura_id=conserje.id,
                    guardia_apertura_id=guardia.id,
                )
                db.add(turno)
                await db.flush()
                habitacion.estado = "Ocupada"
                db.add(
                    EventoHabitacion(
                        habitacion_id=habitacion.id,
                        estado_anterior="Libre",
                        estado_nuevo="Ocupada",
                        origen=TURNO,
                        turno_id=turno.id,
                        operador_id=conserje.id,
                        creado_en=inicio_turno,
                    )
                )
            await db.commit()
        print(f"{CODIGO}: {len(a_ocupar)} habitaciones tomadas; quedan {len(libres) - len(a_ocupar)} disponibles.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(llenar(int(sys.argv[1]) if len(sys.argv) > 1 else 1))
