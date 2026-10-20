import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.deps import operador_actual
from app.api.v1.endpoints import articulos, auth, guardias, habitaciones, turnos
from app.core.config import settings
from app.services.estadia import ciclo_depuracion

# Encabezado que solo envía la aplicación (services/api.ts). Un formulario o enlace de otro sitio no puede
# agregarlo, y CORS impide que un script de otro origen lo envíe: es la protección contra CSRF de las
# peticiones que modifican datos, junto con la cookie SameSite=Strict.
ENCABEZADO_APP = ("X-Requested-With", "motelos")
METODOS_QUE_MODIFICAN = {"POST", "PUT", "PATCH", "DELETE"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    # RNF-08: depuración periódica de las patentes de turnos cerrados.
    tarea = asyncio.create_task(ciclo_depuracion())
    try:
        yield
    finally:
        tarea.cancel()


es_produccion = settings.ENTORNO == "produccion"
app = FastAPI(
    title=settings.PROJECT_NAME,
    version="2.0.0",
    lifespan=lifespan,
    # En producción no se publica la documentación interactiva de la API.
    docs_url=None if es_produccion else "/docs",
    redoc_url=None,
    openapi_url=None if es_produccion else "/openapi.json",
)


@app.middleware("http")
async def exigir_encabezado_de_la_aplicacion(request: Request, call_next):
    nombre, valor = ENCABEZADO_APP
    if (
        request.method in METODOS_QUE_MODIFICAN
        and request.url.path.startswith("/api/")
        and request.headers.get(nombre) != valor
    ):
        return JSONResponse(
            status_code=403, content={"detail": "Petición rechazada: falta el encabezado de la aplicación."}
        )
    return await call_next(request)


# CORS se agrega después para quedar por fuera: también las respuestas 403 llevan sus encabezados.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", ENCABEZADO_APP[0]],
)

# Todas las rutas de la API exigen sesión, salvo el inicio y el cierre de sesión.
con_sesion = [Depends(operador_actual)]
app.include_router(auth.router, prefix="/api/v1/auth", tags=["sesión"])
app.include_router(habitaciones.router, prefix="/api/v1/habitaciones", tags=["habitaciones"], dependencies=con_sesion)
app.include_router(turnos.router, prefix="/api/v1/turnos", tags=["turnos"], dependencies=con_sesion)
app.include_router(articulos.router, prefix="/api/v1/articulos", tags=["articulos"], dependencies=con_sesion)
app.include_router(guardias.router, prefix="/api/v1/guardias", tags=["caja"], dependencies=con_sesion)


@app.get("/health")
def health_check():
    return {"status": "ok"}
