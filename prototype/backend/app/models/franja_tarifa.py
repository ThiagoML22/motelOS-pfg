from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, SmallInteger, String, Time, func, text

from app.core.database import Base
from app.core.inquilino import DeEstablecimiento

ACTIVA = text("activa")


class FranjaTarifa(DeEstablecimiento, Base):
    """Cuándo rige una tarifa especial de una categoría (migración 014): «viernes y sábado de 20 a 6».

    `dias` es una máscara de los días de COMIENZO (lunes = 1 ... domingo = 64): la franja de la noche del viernes sigue
    rigiendo el sábado a las 2. `desde == hasta` es el día completo. El precio no vive acá: es la fila de tarifas con
    este franja_id que esté vigente, y se reemplaza como cualquier tarifa. Una franja se da de baja, no se borra.

    La base no deja que dos franjas activas de una categoría se pisen (franjas_tarifa_sin_superposicion).
    """

    __tablename__ = "franjas_tarifa"
    __table_args__ = (
        Index(
            "franjas_tarifa_nombre",
            "establecimiento_id",
            "categoria_id",
            func.lower(text("nombre")),
            unique=True,
            postgresql_where=ACTIVA,
            sqlite_where=ACTIVA,
        ),
    )

    id = Column(Integer, primary_key=True)
    categoria_id = Column(Integer, ForeignKey("categorias_habitacion.id"), nullable=False)
    nombre = Column(String(40), nullable=False)
    dias = Column(SmallInteger, nullable=False)
    desde = Column(Time, nullable=False)
    hasta = Column(Time, nullable=False)
    activa = Column(Boolean, nullable=False, default=True)
    creada_por_id = Column(Integer, ForeignKey("operadores.id"), nullable=True)
    creada_en = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
