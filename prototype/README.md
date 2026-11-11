# Motel C.C. — TPS (Sistema de Procesamiento de Transacciones)
### Prototipo v3 · Versión de la AE4: configuración, varios establecimientos, inteligencia local y operación diaria

> **Para instalarlo y verificarlo, seguir el [manual de despliegue](MANUAL_DESPLIEGUE.md).** Este archivo describe el sistema; el manual tiene los pasos completos, los usuarios de demostración y el recorrido de verificación.

---

## 1. Identificación del proyecto
* **Denominación del proyecto:** Sistema de Procesamiento de Transacciones orientado a alojamientos transitorios por hora — Caso Motel C.C.
* **Asignatura:** Proyecto Final de Grado · Comisión A · Sede Posadas · Universidad de la Cuenca del Plata
* **Docente titular:** PosDr. Darío Ezequiel Díaz
* **Autor:** Thiago Martino Leal (proyecto individual)
* **Actividad y etiqueta:** Actividad de Evaluación N.º 4 (AE4) · prototipo v3 (etiqueta `v3`). Se integró por etapas en la rama `ae4/v3` (solicitudes #22 a #27 y la de entrega). Las etiquetas `v2` (AE3) y `v1.2` (AE2) siguen disponibles.

---

## 2. Qué hace este prototipo

### Lo que agrega el v3 (Sprint 4, migraciones 005 a 017; todo validado con la gerencia en las actas del 27/10 y del 11/11/2026)

| Requisito o función | Qué hace el v3 |
| :--- | :--- |
| RF-11 ampliado | **Panel de configuración** de la gerencia: tarifas (que se reemplazan, nunca se editan), artículos, habitaciones, alta y baja de conserjes y fondo de cambio. Rige hacia adelante (RN-DER-06) |
| Categorías y tarifas especiales | Cada categoría de habitación tiene su tarifa, y puede tener tarifas especiales por día y hora; la base impide que dos se pisen. El turno guarda la tarifa con la que empezó |
| RF-10 | Comprobante de arqueo en PDF, con huella SHA-256 encadenada y QR para verificarlo (comprobantes verificables) |
| RNF-09 | Si se corta la conexión, la interfaz lo avisa en pocos segundos, bloquea abrir y cobrar, y se recupera sola sin cerrar la sesión |
| Varios establecimientos | Base compartida con `establecimiento_id` en cada tabla y Row Level Security con el establecimiento del token firmado; un usuario de plataforma da de alta y suspende moteles |
| Registro de actividad | Lo que cambia la gerencia y lo que hacen los conserjes queda registrado, de solo agregado |
| Inteligencia local y Mot | Pronóstico, alertas, sugerencias de tarifa, reposición, gemelo del motel y un asistente en español que responde y propone acciones (la interfaz las confirma). Todo corre en el servidor del motel, sin servicios externos |
| Página del cliente | Ticket con QR de enlace firmado, sin cuenta ni datos personales: estadía, pedidos al minibar, pedir la cuenta, calificación anónima |
| Operación diaria | Traslado de turno, arreglos por habitación, traspaso de guardia y recuento de toallas y sábanas, a ciegas y obligatorio al cerrar |
| RF-12 | La grilla marca «Demora de limpieza» con los minutos en las habitaciones que pasan más de 30 min En Limpieza. Los minutos los calcula el servidor con el historial de estados (`DEMORA_LIMPIEZA_MIN`) |

RNF-06 y el despliegue en la nube quedan en la hoja de ruta. El detalle está en el informe (Capítulos IX, XI y XIII).

### Lo que viene del v2
El v2 se construye sobre el esqueleto del v1 (apertura de turno, consumos con descuento atómico de stock, liquidación por tiempo, cobro desglosado y cierre inmutable) y agrega el control que da sentido al sistema: **el cierre de caja ciego por guardia**.

| Requisito o regla | Qué hace el v2 |
| :--- | :--- |
| RNF-04 | Cada conserje entra con su usuario y su clave. La sesión es un JWT en una cookie `httpOnly` y `SameSite=Strict`; cada turno, consumo, cobro y arqueo queda a nombre del operador de la sesión. Roles: `OPERADOR` (conserje) y `ADMINISTRADOR` (gerencia). |
| RF-08 | Hay **un conserje responsable por guardia** (06:00, 14:00 o 22:00), y todas las operaciones de la guardia quedan a su nombre. Al terminar declara el **monto total** del efectivo, que incluye el fondo de cambio de $25.000, y los comprobantes de POSNET y Mercado Pago, **sin ver el total del sistema**. Al confirmar se guarda el arqueo, se cierra la guardia y recién entonces se muestra el resultado. |
| RN-RES-03 | Ninguna respuesta de la API muestra el total de una guardia abierta, ni al conserje ni a la gerencia. Hay una prueba automática que recorre todas las rutas de consulta. |
| RF-09 y RN-DER-03 | Diferencia = total declarado − total del sistema: «Correcto» si es 0, «Faltante» si es negativa y «Sobrante» si es positiva. La gerencia ve los arqueos, el detalle de cobros de cada guardia, las métricas por conserje y la TDC medida por el sistema. |
| RN-DER-04 | Un cobro entra a la caja de la guardia que atiende en ese momento, aunque el turno lo haya abierto la guardia anterior (el turno de 21:30 que se cobra a las 23:30 entra a la guardia de las 22:00). |
| RN-RES-02 | En PostgreSQL, un arqueo confirmado no admite `UPDATE` ni `DELETE`, una guardia cerrada no se reabre ni recibe pagos, y la base recalcula el total del sistema, la diferencia y la categoría: lo que envíe la aplicación en esas columnas se reemplaza. |
| Cierre supervisado | Si un conserje se va sin cerrar su guardia, la gerencia la cierra contando la gaveta, también a ciegas y con un motivo obligatorio. El arqueo sigue siendo de la caja del conserje y registra quién lo confirmó. |
| RNF-02 | Apertura y cobro con un percentil 95 de 800 ms o menos (5 + 5 peticiones concurrentes, 20 repeticiones). |
| RNF-07 | Cobertura de 70 % o más en los módulos de liquidación y caja; el canal falla si baja. |

Se mantienen del v1: RNF-01 (inmutabilidad de turnos, pagos y consumos cerrados), RNF-03 (sin datos personales de los clientes) y RNF-08 (la patente se elimina a las 24 h del cierre).

---

## 3. Requisitos previos
Docker con Compose y Git. Las versiones exactas de referencia y las que fija el repositorio (Python 3.12.16, Node.js 20.20.2, PostgreSQL 16.15) están en el [manual de despliegue](MANUAL_DESPLIEGUE.md), sección 2.

---

## 4. Instalación (resumen; el detalle está en el manual)
```bash
git clone https://github.com/ThiagoML22/motelOS-pfg.git
cd motelOS-pfg
git checkout v3
cd prototype
cp .env.example .env
docker compose up --build -d
docker compose --profile admin run --rm admin
docker compose --profile admin run --rm admin scripts.cargar_historial
```

El penúltimo comando crea los establecimientos `motelcc` y `luna` con sus usuarios (`gerencia`, `conserje1`, `conserje2`) y el usuario `plataforma`, con el usuario dueño de la base; el último carga el historial de ejemplo. Las claves de demostración están en `.env.example` (sección 7 del manual). La API nunca recibe las credenciales del dueño.

Para detener: `docker compose down`. Para empezar de cero (borra la base): `docker compose down -v`.

**Problemas frecuentes**
* **Puertos ocupados:** cambiar `DB_PORT`, `API_PORT` y `WEB_PORT` en `.env`, y ajustar `VITE_API_URL` y `CORS_ORIGINS` al nuevo puerto.
* **Esquema desactualizado:** las migraciones se aplican solo sobre una base vacía. Al pasar de una versión anterior, ejecutar `docker compose down -v` y volver a levantar.
* **«No hay una guardia abierta»:** el conserje tiene que abrir su guardia antes de operar.

---

## 5. Configuración (archivo `.env`)
| Variable | Función | Valor de ejemplo |
| :--- | :--- | :--- |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Usuario dueño de las tablas (migraciones) y base | `postgres` / `postgres` / `motel_db` |
| `APP_DB_USER` / `APP_DB_PASSWORD` | Rol de la aplicación, sin propiedad de las tablas | `motel_app` / `motel_app` |
| `DB_PORT` / `API_PORT` / `WEB_PORT` | Puertos publicados, solo en `127.0.0.1` | `5432` / `8000` / `5173` |
| `VITE_API_URL` / `CORS_ORIGINS` | Dirección de la API para la interfaz y origen autorizado | `http://localhost:8000/api/v1` / `http://localhost:5173` |
| `ENTORNO` | `desarrollo` o `produccion`. En producción se exige un `JWT_SECRET` propio de 32 caracteres o más y `COOKIE_SECURE=True`, y no se publica `/docs` | `desarrollo` |
| `JWT_SECRET` | Clave de firma de las sesiones | valor de desarrollo |
| `COOKIE_SECURE` | La cookie de sesión viaja solo por HTTPS | `False` en local |
| `FONDO_INICIAL_CAJA` | Fondo de cambio de respaldo, en pesos. Desde la migración 005 el fondo vive en la base (`configuracion_caja`, $25.000) y la gerencia lo cambia desde **Configuración**; esta variable rige solo si esa fila falta | `25000` |
| `URL_PUBLICA` | Dirección de la ventanilla para los QR (vacía: la de `CORS_ORIGINS`) | vacía |
| `EXIGIR_RECUENTO_ROPA` | Recuento de toallas y sábanas obligatorio al abrir y cerrar la guardia | `True` |
| `DEMO_CLAVE_GERENCIA` / `DEMO_CLAVE_CONSERJES` / `DEMO_CLAVE_PLATAFORMA` | Claves de los usuarios de demostración (vacías: se generan al azar) | ver `.env.example` |

Otros parámetros con valor por defecto en `backend/app/core/config.py`, listados y comentados al final de `.env.example`: duración de la sesión (9 h), bloqueo tras 5 intentos fallidos durante 15 min, zona horaria del motel, retención de la patente (24 h).

Los conserjes se dan de alta y de baja desde **Configuración → Conserjes** (RF-11). El alta de un gerente y el cambio de clave se hacen con el usuario dueño (la clave se pide por teclado):
```bash
docker compose --profile admin run --rm admin scripts.crear_operador --usuario conserje3 --nombre "Conserje 3"
docker compose --profile admin run --rm admin scripts.crear_operador --usuario conserje3 --restablecer-clave
```

---

## 6. Ejecución y verificación

### A. Direcciones
* Interfaz: `http://localhost:5173` · API: `http://localhost:8000/docs` (solo en desarrollo)

### B. Recorrido manual (a 1366 × 768)
El recorrido de verificación del v3, paso por paso y con los requisitos que acredita, está en el [manual de despliegue](MANUAL_DESPLIEGUE.md), sección 8. El de abajo es el del v2, con el código de establecimiento `motelcc`:

1. **Ingreso:** entrar como `conserje1`. Sin guardia abierta, la pantalla ofrece **Abrir guardia**.
2. **Operación:** abrir un turno en una habitación libre, agregar productos y cobrar (v1). En la cuenta del turno figura quién lo abrió.
3. **Cierre ciego:** en **Cierre de caja**, cargar el efectivo total (con el fondo de $25.000) y los comprobantes. La pantalla no muestra el total del sistema. Al confirmar aparece el comprobante con lo declarado, lo registrado y la diferencia clasificada, que se puede imprimir.
4. **Recambio:** entrar como `conserje2`, abrir la guardia siguiente y cobrar un turno que abrió `conserje1`: el cobro entra a la caja de `conserje2` (RN-DER-04).
5. **Gerencia:** entrar como `gerencia`, en **Control de caja**: arqueos, detalle de cobros, métricas por conserje y TDC.
6. **Configuración (RF-11):** como `gerencia`, en **Configuración**: cambiar la tarifa (el historial muestra la anterior), el fondo de cambio, el precio de un artículo; agregar la habitación 14 (aparece en la grilla) y dar de alta y de baja un conserje. Los turnos, consumos y guardias ya registrados conservan sus valores (RN-DER-06).

### C. Verificación automática
```bash
# Pruebas (SQLite en memoria; en el canal, sobre PostgreSQL 16) con cobertura de liquidación y caja
cd backend && python -m pytest --cov --cov-config=.coveragerc

# Migraciones y verificaciones SQL sobre un PostgreSQL 16 descartable (Windows, requiere Docker)
powershell -File db/verificar_local.ps1

# Recorrido de punta a punta y latencia contra la API levantada (base recién creada y operadores de demostración)
cd backend && python -m scripts.recorrido_v2 --api http://localhost:8000
cd backend && python -m scripts.medir_latencia --api http://localhost:8000 --salida latencia.csv
cd backend && python -m scripts.recorrido_panel --api http://localhost:8000
cd backend && python -m scripts.recorrido_multiinquilino --api http://localhost:8000
cd backend && python -m scripts.recorrido_categorias_perfil --api http://localhost:8000
cd backend && python -m scripts.recorrido_inteligencia_novedades --api http://localhost:8000
```

Los recorridos necesitan los usuarios de demostración y `EXIGIR_RECUENTO_ROPA=False` en la API, porque abren y cierran guardias sin contar la ropa (el recuento se prueba en `test_operacion.py`).

Comprobación de RN-RES-02 desde SQL (el motor rechaza la sentencia):
```bash
docker compose exec db psql -U postgres -d motel_db -c "UPDATE arqueos_caja SET diferencia = 0;"
```

---

## 7. Canal de integración continua
[`.github/workflows/ci.yml`](../.github/workflows/ci.yml), en cada `push` y `pull_request` sobre `main` y sobre las ramas de integración (`ae3/v2`, `ae4/v3`):

* **Backend (Python 3.12 y PostgreSQL 16):**
  * Ruff y `pip-audit` (falla si hay vulnerabilidades publicadas).
  * Pruebas sobre PostgreSQL con corte de cobertura en 70 % (RNF-07): 626 en el v3, con 96,7 % de cobertura de liquidación y caja.
  * Las migraciones 001 a 017 y 16 verificaciones SQL con el rol `motel_app` (inmutabilidad, permisos, cierre de caja, panel, aislamiento entre establecimientos, sellos, tarifas especiales, operación y recuento de ropa, entre otras), más la migración desde una base v1.2 con datos.
  * Seis recorridos de punta a punta con la API corriendo como `motel_app` sobre el esquema migrado, y la medición de latencia de RNF-02, que se guarda como artefacto de la corrida.
* **Frontend (Node 20):** `npm audit` de las dependencias de producción, verificación de tipos y compilación.

---

## 8. Limitaciones conocidas de esta versión
* **Guardia abandonada:** si un conserje se va sin cerrar su guardia, el siguiente no puede operar. La gerencia la cierra desde **Control de caja → Cierre supervisado**: cuenta la gaveta sin ver el total, escribe el motivo (obligatorio) y el arqueo queda en la caja del conserje, marcado como supervisado y con el nombre de quien lo confirmó (migración 003). La gerencia aprobó el procedimiento como RF-14 en el acta del 19/10/2026.
* **Un responsable por guardia:** la gerencia definió el 19/10/2026 que trabaja un solo conserje por guardia y que todas las operaciones de la guardia van a su nombre. Por eso no se implementan cajas simultáneas ni la confirmación de cada cobro con PIN, que la gerencia no aprobó.
* **Lo que el cierre ciego no impide:** el conserje ve el importe de cada turno que cobra (lo necesita para cobrar). Podría anotarlos y sumarlos, como hoy con el papel; el sistema impide que el total se lo dé el software.
* **Sesión:** cerrar sesión borra la cookie, pero un token copiado sigue siendo válido hasta su vencimiento (9 h), salvo que el operador se desactive. Se mitiga con `httpOnly`, `SameSite=Strict` y HTTPS en producción.
* **Bloqueo por intentos:** el bloqueo temporal solo existe para usuarios reales, de modo que un atacante persistente podría inferir qué usuarios existen. Se acepta: los usuarios no son secretos en un local con tres conserjes.
* **Dependencias de compilación del frontend:** `npm audit` informa vulnerabilidades en Vite 5 y Tailwind 3, que solo corren en la máquina de desarrollo y no llegan al navegador. Su corrección exige cambiar de versión mayor (Vite 8, Tailwind 4) y queda en la hoja de ruta, junto con el despliegue de la versión compilada.
* **Servidor de desarrollo:** el v3 se ejecuta con los servidores de desarrollo de Uvicorn y Vite (recarga automática). Para producción falta la imagen compilada detrás de un proxy con HTTPS; queda en la hoja de ruta, con RNF-06 (disponibilidad) y el despliegue en la nube.
* **Claves de demostración:** `.env.example` trae claves de prueba para que el manual de despliegue se pueda seguir sin asistencia. No son credenciales reales; se cambian antes de cargar datos reales.
* **Fuera del v3:** disponibilidad medida (RNF-06) y despliegue en la nube.

---

## 9. Declaración de herramientas auxiliares
Conforme al Protocolo de Uso Autorizado de Inteligencia Artificial:

* **Herramienta:** Claude Code, la única herramienta de asistencia que usa el autor, en todo el código del prototipo.
* **Trailer en los commits:**
  * Llevan el trailer `Co-Authored-By: Claude Code` los commits de la v1 a la v2, los del panel de configuración (RF-11) y los de integración y entrega del v3.
  * No lo llevan los 34 commits de la demo del Sprint 4 (02/11 al 10/11/2026, de a8595a1 a 80e5806, integrados en las solicitudes #22 a #27), aunque también se hicieron con Claude Code.
  * No se reescribieron, para conservar sus hashes y sus fechas. Su declaración, commit por commit, está en la Bitácora Individual de la AE4.
* **Uso en el v2:** implementación de la migración 002 y las verificaciones SQL, la autenticación, el servicio de caja y los reportes, las pantallas de ingreso, guardia, cierre de caja y gerencia, las pruebas, los scripts de recorrido y de latencia, y este archivo.
* **Uso en el v3:**
  * Migraciones 005 a 017 y sus verificaciones SQL.
  * Servicios y rutas del panel, del multiinquilino, del registro de actividad, del PDF, de la inteligencia local y del asistente.
  * Página del cliente, operación diaria, pantallas, pruebas, recorridos, el manual de despliegue y este archivo.
* **Decisiones del autor en el v3:**
  * El alcance del panel, aprobado por la gerencia el 27/10/2026.
  * Los permisos por columna en lugar de funciones SECURITY DEFINER o un segundo rol.
  * El multiinquilino con base compartida y RLS.
  * Que la inteligencia y el asistente corran sin servicios externos.
  * Que el asistente proponga y no ejecute (el cobro queda afuera).
  * Las funciones de operación pedidas por el autor a partir del relevamiento.
* **Decisiones del autor:** el cierre ciego por guardia, la imputación del cobro a la guardia que atiende, los roles, la separación entre el dueño de las tablas y el rol de la aplicación y las preguntas abiertas para la gerencia.
* **Verificación:**
  * 626 pruebas automáticas en PostgreSQL 16 (624 en SQLite).
  * 16 verificaciones SQL con el rol de la aplicación.
  * Seis recorridos de punta a punta contra la API.
  * La medición de latencia.
  * El recorrido del manual de despliegue sobre un clon limpio, a 1366 × 768.

  El detalle por commit (herramienta, función, fecha y verificación) está en la bitácora individual.
