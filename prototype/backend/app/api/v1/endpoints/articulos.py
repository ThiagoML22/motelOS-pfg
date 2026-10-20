from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api.deps import solo_administrador
from app.core.database import get_db
from app.models.articulo import Articulo
from app.schemas.articulo import ArticuloCreate, ArticuloResponse

router = APIRouter()


@router.get("/", response_model=list[ArticuloResponse])
async def get_articulos(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Articulo).order_by(Articulo.descripcion))
    return result.scalars().all()


# El alta de artículos (precio y stock inicial) es una decisión de la gerencia, no del conserje.
@router.post(
    "/",
    response_model=ArticuloResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(solo_administrador)],
)
async def create_articulo(articulo_in: ArticuloCreate, db: AsyncSession = Depends(get_db)):
    query = await db.execute(select(Articulo).where(Articulo.codigo == articulo_in.codigo))
    if query.scalars().first():
        raise HTTPException(status_code=400, detail="El código de artículo ya existe.")

    nuevo_articulo = Articulo(**articulo_in.model_dump())
    db.add(nuevo_articulo)
    await db.commit()
    await db.refresh(nuevo_articulo)
    return nuevo_articulo
