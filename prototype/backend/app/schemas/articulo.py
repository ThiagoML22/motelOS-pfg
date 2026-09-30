from pydantic import BaseModel, ConfigDict, Field


class ArticuloBase(BaseModel):
    codigo: str = Field(min_length=1, max_length=50)
    descripcion: str = Field(min_length=1, max_length=255)
    precio_unitario: float = Field(ge=0)
    stock_actual: int = Field(ge=0)
    categoria: str | None = None


class ArticuloCreate(ArticuloBase):
    pass


class ArticuloResponse(ArticuloBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class ConsumoCreate(BaseModel):
    articulo_id: int
    cantidad: int = Field(gt=0)


class ConsumoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    articulo_id: int
    cantidad: int
    precio_unitario: float
    subtotal: float
