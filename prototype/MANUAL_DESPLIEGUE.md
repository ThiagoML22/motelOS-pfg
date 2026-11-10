# Manual de despliegue · MotelOS, prototipo v3

Este manual permite que una persona que no escribió el sistema lo clone, lo levante y lo verifique sin ayuda. Sigue las once secciones de la guía de comprobación de ejecutabilidad de la AE4. Todo comando se ejecuta tal como está escrito; si algún paso exige algo que este manual no dice, es un defecto del manual.

---

## 1. Propósito y versión

**Sistema:** MotelOS, sistema de procesamiento de transacciones para alojamientos transitorios por hora (caso Motel C.C.). Proyecto Final de Grado de Thiago Martino Leal, UCP, Sede Posadas.

**Versión:** prototipo v3, etiqueta `v3` del repositorio https://github.com/ThiagoML22/motelOS-pfg.

**Alcance de esta versión:**
- Lo de las versiones anteriores: turnos, consumos, cobro desglosado, inmutabilidad, cierre de caja ciego por guardia, panel de la gerencia.
- **Panel de configuración** (RF-11).
- **Comprobante de arqueo en PDF** (RF-10).
- **Recuperación al reconectar** (RNF-09).
- **Varios establecimientos en una base compartida**, con Row Level Security.
- Categorías de habitación con su tarifa y tarifas especiales por día y hora.
- Inteligencia local de la gerencia y asistente (Mot), sin servicios externos.
- Comprobantes verificables, página del cliente con QR y operación diaria (traslados, arreglos, traspaso de guardia, recuento de ropa).

---

## 2. Requisitos previos

Sistema de referencia en el que se probó este manual:

| Elemento | Versión exacta |
|---|---|
| Sistema operativo | Windows 11 Pro (también corre en Linux o macOS con Docker) |
| Docker Engine (Docker Desktop) | 29.8.0 |
| Docker Compose | v5.5.1 (mínimo 2.24, por la sintaxis de los archivos) |
| Git | 2.55.0 |

Las versiones del lenguaje y del motor quedan fijadas en los archivos del repositorio. No hace falta instalarlas: las trae Docker.

| Componente | Versión | Dónde se fija |
|---|---|---|
| Python | 3.12.16 | `backend/Dockerfile` (`python:3.12.16-slim`) |
| Node.js / npm | 20.20.2 / 10.8.2 | `frontend/Dockerfile` (`node:20.20.2-alpine`) |
| PostgreSQL | 16.15 | `docker-compose.yml` (`postgres:16.15`) |
| Dependencias de Python | versiones exactas | `backend/requirements.txt` |
| Dependencias de JavaScript | archivo de bloqueo | `frontend/package-lock.json` (se instala con `npm ci`) |

Puertos libres en la máquina: 5432, 8000 y 5173. Si alguno está ocupado, ver la sección 4.

---

## 3. Obtención del código

```bash
git clone https://github.com/ThiagoML22/motelOS-pfg.git
cd motelOS-pfg
git checkout v3
cd prototype
```

Para comprobar la etiqueta: `git show --no-patch v3` muestra el commit y su fecha.

---

## 4. Configuración

```bash
cp .env.example .env
```

En Windows con PowerShell: `Copy-Item .env.example .env`.

El archivo de ejemplo funciona tal como está. Todas sus claves son de demostración y ninguna es real.

| Variable | Qué significa | Valor de ejemplo |
|---|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Usuario dueño de las tablas (aplica las migraciones y carga la demostración) y nombre de la base | `postgres`, `postgres`, `motel_db` |
| `APP_DB_USER`, `APP_DB_PASSWORD` | Rol con el que se conecta la API: no es dueño de las tablas | `motel_app`, `motel_app` |
| `DATABASE_URL` | Dirección de la base para correr la API fuera de Docker (con Docker la arma el compose) | `postgresql+asyncpg://motel_app:motel_app@db:5432/motel_db` |
| `SQL_ECHO` | Muestra las consultas SQL en el registro | `False` |
| `DB_PORT`, `API_PORT`, `WEB_PORT` | Puertos publicados, solo en `127.0.0.1` | `5432`, `8000`, `5173` |
| `VITE_API_URL` | Dirección de la API que usa la interfaz | `http://localhost:8000/api/v1` |
| `CORS_ORIGINS` | Dirección de la interfaz autorizada por la API | `http://localhost:5173` |
| `ENTORNO` | `desarrollo` o `produccion`. En producción se exige un `JWT_SECRET` propio y `COOKIE_SECURE=True` | `desarrollo` |
| `JWT_SECRET` | Clave de firma de las sesiones | valor de desarrollo |
| `COOKIE_SECURE` | La cookie de sesión viaja solo por HTTPS | `False` |
| `FONDO_INICIAL_CAJA` | Fondo de cambio de respaldo; el vigente lo fija la gerencia | `25000` |
| `URL_PUBLICA` | Dirección para los QR (vacía: la de `CORS_ORIGINS`) | vacía |
| `EXIGIR_RECUENTO_ROPA` | Recuento de toallas y sábanas al abrir y cerrar la guardia | `True` |
| `DEMO_CLAVE_GERENCIA`, `DEMO_CLAVE_CONSERJES`, `DEMO_CLAVE_PLATAFORMA` | Claves de los usuarios de demostración (sección 7) | `demo-gerencia-2026`, `demo-conserje-2026`, `demo-plataforma-2026` |

Al final de `.env.example`, comentados, están los parámetros con valor por defecto: duración de la sesión, bloqueo por intentos, zona horaria, retención de la patente y otros.

**Si un puerto está ocupado:** cambiar `DB_PORT`, `API_PORT` o `WEB_PORT` en `.env`, y ajustar `VITE_API_URL` y `CORS_ORIGINS` al puerto nuevo. Por ejemplo, con `API_PORT=8010` y `WEB_PORT=5180`, quedan `VITE_API_URL=http://localhost:8010/api/v1` y `CORS_ORIGINS=http://localhost:5180`.

---

## 5. Base de datos

**Crear el esquema.** No hay que ejecutar nada a mano. Al crear la base vacía, PostgreSQL aplica en orden, con el usuario dueño, las migraciones `db/migraciones/001_esquema_v1.sql` a `017_recuento_de_ropa.sql`. Ocurre durante el primer arranque (sección 6).

**Cargar los datos de demostración:** después del arranque, con la base ya creada.

```bash
docker compose --profile admin run --rm admin
docker compose --profile admin run --rm admin scripts.cargar_historial
```

- **Primer comando:** crea los dos establecimientos del escenario (Motel C.C., código `motelcc`, con 13 habitaciones en tres categorías; Motel Luna, código `luna`) y sus usuarios.
- **Segundo comando:** carga un historial de ejemplo (60 días en Motel C.C. y 30 en Motel Luna) para el análisis de la gerencia. Es opcional, pero sin él la sección Inteligencia queda casi vacía.
- **Repetirlos:** los dos se pueden ejecutar de nuevo sin duplicar nada.
- **Datos de personas:** ninguno es real. Los usuarios son genéricos y los clientes no tienen datos personales (RNF-03).

**Empezar de cero:** `docker compose down -v` borra la base, y en el próximo arranque se vuelven a aplicar las migraciones.

---

## 6. Ejecución

```bash
docker compose up --build -d
```

- **La primera vez** tarda unos minutos, porque construye las imágenes e instala las dependencias.
- **Contenedores que levanta:** la base (`db`), la API (`backend`) y la interfaz (`frontend`).
- **Esperar la API:** antes de cargar la demostración (sección 5), esperar a que responda la prueba de humo (sección 8).

| Qué | Dirección |
|---|---|
| Interfaz | http://localhost:5173 |
| API | http://localhost:8000 (documentación interactiva en `/docs`, solo en desarrollo) |
| Base | `127.0.0.1:5432` |

**Orden completo, desde cero:**

```bash
docker compose up --build -d
docker compose --profile admin run --rm admin
docker compose --profile admin run --rm admin scripts.cargar_historial
```

**Detener:**
- `docker compose down` detiene los contenedores y conserva los datos.
- `docker compose down -v` borra también la base.

**Ver los registros:** `docker compose logs backend`.

---

## 7. Usuarios de demostración

Para entrar, la pantalla pide **Establecimiento**, **Usuario** y **Clave**. Las claves son las de `.env`; con el archivo de ejemplo sin cambios son estas:

| Establecimiento | Usuario | Clave | Rol |
|---|---|---|---|
| `motelcc` | `gerencia` | `demo-gerencia-2026` | Gerencia (ADMINISTRADOR) |
| `motelcc` | `conserje1` | `demo-conserje-2026` | Conserje (OPERADOR) |
| `motelcc` | `conserje2` | `demo-conserje-2026` | Conserje (OPERADOR) |
| `luna` | `gerencia`, `conserje1` | las mismas | Otro establecimiento, con otros datos |
| `plataforma` | `plataforma` | `demo-plataforma-2026` | Alta y suspensión de establecimientos |

Son claves de prueba de este ejemplo, no credenciales reales. Si en `.env` se dejan vacías, el primer comando de la sección 5 las genera al azar y las muestra una sola vez en la consola.

---

## 8. Verificación

**Prueba de humo:**

```bash
curl http://localhost:8000/health
```

Responde `{"status":"ok"}`. En PowerShell: `Invoke-RestMethod http://localhost:8000/health`, que muestra `status ok`.

Después, http://localhost:5173 muestra la pantalla de ingreso.

**Recorrido mínimo de los casos «Must»** (pantalla de 1366 × 768 o más):

| # | Paso | Requisito |
|---|---|---|
| 1 | Entrar con `motelcc` / `conserje1`. La pantalla muestra lo que deja la guardia anterior y pide la ropa: confirmar las cantidades y tocar **Recibí y abrir guardia** | RNF-04, RF-08 |
| 2 | La grilla muestra las habitaciones con su estado (Disponible en verde) | RF-01, RNF-05 |
| 3 | Tocar una habitación disponible y abrir un turno: pasa a Ocupada y empieza el cronómetro | RF-02 |
| 4 | En el turno abierto, agregar un consumo del minibar: la cuenta suma y baja el stock. Con un artículo sin stock, el sistema lo rechaza | RF-04, RF-05 |
| 5 | Pasar el turno a Limpieza sin cobrar: se rechaza por la deuda | RF-07 |
| 6 | Cobrar: elegir el medio de pago; con POSNET o Mercado Pago pide el número de comprobante. Al quedar en cero, emite la constancia | RF-03, RF-06 |
| 7 | **Cierre de caja:** contar la ropa a ciegas, declarar el efectivo (con el fondo de $25.000) y los comprobantes, sin ver el total del sistema. Al confirmar se ve la diferencia clasificada y se descarga el PDF | RF-08, RF-09, RF-10 |
| 8 | Entrar con `motelcc` / `gerencia`: en **Control de caja** se ven el arqueo recién hecho, el detalle de cobros y la TDC. En **Configuración** se cambia la tarifa de una categoría y queda el historial | RF-09, RF-11 |
| 9 | Entrar con `luna` / `gerencia`: otro motel, con otros datos. Lo de `motelcc` no aparece | multiinquilino |
| 10 | Detener la API con `docker compose stop backend` con la ventanilla abierta: a los pocos segundos aparece el aviso. Con `docker compose start backend` se recupera sola, sin cerrar la sesión | RNF-09 |

---

## 9. Pruebas automatizadas

**Con Docker, sin instalar nada:**

```bash
docker compose run --rm --no-deps backend sh -c "pip install -q -r requirements-dev.txt && python -m pytest -q"
```

Instala las herramientas de prueba (`requirements-dev.txt`) en un contenedor descartable y corre las pruebas sobre SQLite en memoria. Resultado esperado: todas pasan; en la v3 son 624 en SQLite. En SQLite, alguna prueba puede fallar muy de vez en cuando porque SQLite lee como número un identificador al azar: al repetir el comando, pasa.

**Verificaciones SQL en un PostgreSQL 16 descartable** (Windows con Docker, desde `prototype/`):

```powershell
powershell -ExecutionPolicy Bypass -File db/verificar_local.ps1
```

Aplica las 17 migraciones y corre las 16 verificaciones SQL con el rol `motel_app` (permisos, inmutabilidad, aislamiento entre establecimientos y demás). Termina con «Todas las verificaciones SQL pasaron.».

**Canal de integración continua (`.github/workflows/ci.yml`):** en cada cambio corre:
- Ruff y `pip-audit`.
- Las pruebas sobre PostgreSQL 16 (626 en la v3, con cobertura de liquidación y caja de 96 % y un corte en 70 %).
- Las 16 verificaciones SQL y la migración desde una base v1.2 con datos.
- Seis recorridos de punta a punta con la API conectada como `motel_app`, y la medición de latencia de RNF-02 (P95 de unos 50 ms contra un umbral de 800 ms).
- `npm audit`, la verificación de tipos y la compilación de la interfaz.

La última corrida en verde se cita en la entrega.

---

## 10. Problemas frecuentes

| Problema | Solución |
|---|---|
| `port is already allocated` al levantar | Otro programa usa ese puerto: cambiar `DB_PORT`, `API_PORT` o `WEB_PORT` en `.env` (sección 4) |
| `Definir JWT_SECRET en .env` | Falta el archivo `.env`: ejecutar `cp .env.example .env` |
| La interfaz abre pero dice «Sin conexión con el servidor» | La API todavía arranca (esperar la prueba de humo) o `VITE_API_URL` no coincide con `API_PORT` |
| «Establecimiento, usuario o clave incorrectos» | Falta cargar la demostración (sección 5), o la clave no es la del `.env` |
| Errores de esquema después de cambiar de versión | Las migraciones se aplican solo sobre una base vacía: `docker compose down -v` y volver a levantar |
| El conserje no puede operar: «no hay una guardia abierta» | Abrirla primero (paso 1 de la sección 8) |
| Otro conserje tiene la guardia abierta | Hay una sola ventanilla: cerrarla con su arqueo, o que la gerencia use el cierre supervisado (Control de caja) |
| Docker Desktop no arranca en Windows | Cerrarlo desde la bandeja del sistema y volver a abrirlo. No usar «Reset to factory defaults», que borra todas las imágenes |
| Cambios en el código que no se ven en la interfaz | En Windows, Vite sondea los archivos cada pocos segundos; si no alcanza, `docker compose restart frontend` |

---

## 11. Terceros e inteligencia artificial

**Componentes de terceros:** la tabla con licencia, versión y motivo de cada uno está en el Capítulo IX del informe. Las versiones exactas son las de `backend/requirements.txt` y `frontend/package-lock.json`. Ninguno requiere claves ni servicios externos: la inteligencia local y el asistente corren en el servidor del motel.

**Inteligencia artificial:**
- **Herramienta:** el código del prototipo se escribió con asistencia de Claude Code, la única herramienta de IA que usa el autor.
- **Declaración:** la misma que en el README (sección 9) y en la Bitácora Individual, que tiene una fila por uso con la pieza afectada, la fecha y la verificación posterior.
- **Commits:** los de las versiones v1 a v2 y los de RF-11 llevan el trailer `Co-Authored-By: Claude Code`. Los commits de la demo del Sprint 4 (02/11 al 10/11/2026) no lo llevan; su declaración está en la bitácora, commit por commit.
