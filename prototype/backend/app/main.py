from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.endpoints import articulos, habitaciones, turnos
from app.core.config import settings

app = FastAPI(title=settings.PROJECT_NAME, version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(habitaciones.router, prefix="/api/v1/habitaciones", tags=["habitaciones"])
app.include_router(turnos.router, prefix="/api/v1/turnos", tags=["turnos"])
app.include_router(articulos.router, prefix="/api/v1/articulos", tags=["articulos"])


@app.get("/health")
def health_check():
    return {"status": "ok"}
