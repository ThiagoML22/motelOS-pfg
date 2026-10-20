# Motel C.C. — TPS (Sistema de Procesamiento de Transacciones)
### Prototipo v2 · Primer incremento funcional con pruebas: cierre de caja ciego

---

## 1. Identificación del proyecto
* **Denominación del proyecto:** Sistema de Procesamiento de Transacciones orientado a alojamientos transitorios por hora — Caso Motel C.C.
* **Asignatura:** Proyecto Final de Grado · Comisión A · Sede Posadas · Universidad de la Cuenca del Plata
* **Docente titular:** PosDr. Darío Ezequiel Díaz
* **Autor:** Thiago Martino Leal (proyecto individual)
* **Actividad y etiqueta:** Actividad de Evaluación N.º 3 (AE3) · prototipo v2 (etiqueta `v2`, a publicar al cerrar la integración). Se integra por etapas en la rama `ae3/v2`; la etiqueta `v1.2` sigue disponible como versión de la AE2.

---

## 2. Qué hace este prototipo
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
* **Docker Engine** ≥ 26 y **Docker Compose** ≥ 2.24
* **Git** ≥ 2.40
* *(Opcional, sin contenedores)*: **Python** 3.12.x, **Node.js** 20.x con npm ≥ 10, **PostgreSQL** 16.x

---

## 4. Instalación
```bash
git clone https://github.com/ThiagoML22/motelOS-pfg.git
cd motelOS-pfg
git checkout v2
cd prototype
cp .env.example .env
docker compose up --build -d
docker compose --profile admin run --rm admin
```

El último comando crea los operadores de demostración (`gerencia`, `conserje1` y `conserje2`) con el usuario dueño de la base. Si `DEMO_CLAVE_GERENCIA` y `DEMO_CLAVE_CONSERJES` están vacías en `.env`, las claves se generan al azar y se muestran **una sola vez** en la consola. La API nunca recibe las credenciales del dueño.

Para detener: `docker compose down`. Para empezar de cero (borra la base): `docker compose down -v`.

**Problemas frecuentes**
* **Puertos ocupados:** cambiar `DB_PORT`, `API_PORT` y `WEB_PORT` en `.env`, y ajustar `VITE_API_URL` y `CORS_ORIGINS` al nuevo puerto.
* **Esquema desactualizado:** las migraciones se aplican solo sobre una base vacía. Si había una base de la v1, ejecutar `docker compose down -v`, o aplicar `db/migraciones/002_v2_caja.sql` con el usuario dueño, sin turnos en curso.
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
| `FONDO_INICIAL_CAJA` | Fondo de cambio que recibe cada caja, en pesos (acta del 19/10/2026) | `25000` |
| `DEMO_CLAVE_GERENCIA` / `DEMO_CLAVE_CONSERJES` | Claves de los operadores de demostración | vacías (se generan) |

Otros parámetros con valor por defecto en `backend/app/core/config.py`: duración de la sesión (9 h), bloqueo tras 5 intentos fallidos durante 15 min, zona horaria del motel, retención de la patente (24 h).

Alta de un operador real o cambio de clave (con el usuario dueño; la clave se pide por teclado):
```bash
docker compose --profile admin run --rm admin scripts.crear_operador --usuario conserje3 --nombre "Conserje 3"
docker compose --profile admin run --rm admin scripts.crear_operador --usuario conserje3 --restablecer-clave
```

---

## 6. Ejecución y verificación

### A. Direcciones
* Interfaz: `http://localhost:5173` · API: `http://localhost:8000/docs` (solo en desarrollo)

### B. Recorrido manual (a 1366 × 768)
1. **Ingreso:** entrar como `conserje1`. Sin guardia abierta, la pantalla ofrece **Abrir guardia**.
2. **Operación:** abrir un turno en una habitación libre, agregar productos y cobrar (v1). En la cuenta del turno figura quién lo abrió.
3. **Cierre ciego:** en **Cierre de caja**, cargar el efectivo total (con el fondo de $25.000) y los comprobantes. La pantalla no muestra el total del sistema. Al confirmar aparece el comprobante con lo declarado, lo registrado y la diferencia clasificada, que se puede imprimir.
4. **Recambio:** entrar como `conserje2`, abrir la guardia siguiente y cobrar un turno que abrió `conserje1`: el cobro entra a la caja de `conserje2` (RN-DER-04).
5. **Gerencia:** entrar como `gerencia`, en **Control de caja**: arqueos, detalle de cobros, métricas por conserje y TDC.

### C. Verificación automática
```bash
# Pruebas (SQLite en memoria; en el canal, sobre PostgreSQL 16) con cobertura de liquidación y caja
cd backend && python -m pytest --cov --cov-config=.coveragerc

# Migraciones y verificaciones SQL sobre un PostgreSQL 16 descartable (Windows, requiere Docker)
powershell -File db/verificar_local.ps1

# Recorrido de punta a punta y latencia contra la API levantada (base recién creada y operadores de demostración)
cd backend && python -m scripts.recorrido_v2 --api http://localhost:8000
cd backend && python -m scripts.medir_latencia --api http://localhost:8000 --salida latencia.csv
```

Comprobación de RN-RES-02 desde SQL (el motor rechaza la sentencia):
```bash
docker compose exec db psql -U postgres -d motel_db -c "UPDATE arqueos_caja SET diferencia = 0;"
```

---

## 7. Canal de integración continua
[`.github/workflows/ci.yml`](../.github/workflows/ci.yml), en cada `push` y `pull_request` sobre `main`:

* **Backend (Python 3.12 y PostgreSQL 16):** Ruff; `pip-audit` (falla si hay vulnerabilidades publicadas); pruebas sobre PostgreSQL con corte de cobertura en 70 % (RNF-07); migraciones y verificaciones SQL de inmutabilidad (`verify_inmutabilidad.sql`), permisos del rol de la aplicación (`verify_roles.sql`), cierre de caja (`verify_caja.sql`) y migración desde una base v1.2 con datos; y un recorrido de punta a punta con la API corriendo como `motel_app` sobre el esquema migrado, más la medición de latencia de RNF-02, que se guarda como artefacto de la corrida.
* **Frontend (Node 20):** `npm audit` de las dependencias de producción, verificación de tipos y compilación.

---

## 8. Limitaciones conocidas de esta versión
* **Guardia abandonada:** si un conserje se va sin cerrar su guardia, el siguiente no puede operar. La gerencia la cierra desde **Control de caja → Cierre supervisado**: cuenta la gaveta sin ver el total, escribe el motivo (obligatorio) y el arqueo queda en la caja del conserje, marcado como supervisado y con el nombre de quien lo confirmó (migración 003). La gerencia aprobó el procedimiento como RF-14 en el acta del 19/10/2026.
* **Un responsable por guardia:** la gerencia definió el 19/10/2026 que trabaja un solo conserje por guardia y que todas las operaciones de la guardia van a su nombre. Por eso no se implementan cajas simultáneas ni la confirmación de cada cobro con PIN, que la gerencia no aprobó.
* **Lo que el cierre ciego no impide:** el conserje ve el importe de cada turno que cobra (lo necesita para cobrar). Podría anotarlos y sumarlos, como hoy con el papel; el sistema impide que el total se lo dé el software.
* **Sesión:** cerrar sesión borra la cookie, pero un token copiado sigue siendo válido hasta su vencimiento (9 h), salvo que el operador se desactive. Se mitiga con `httpOnly`, `SameSite=Strict` y HTTPS en producción.
* **Bloqueo por intentos:** el bloqueo temporal solo existe para usuarios reales, de modo que un atacante persistente podría inferir qué usuarios existen. Se acepta: los usuarios no son secretos en un local con tres conserjes.
* **Dependencias de compilación del frontend:** `npm audit` informa vulnerabilidades en Vite 5 y Tailwind 3, que solo corren en la máquina de desarrollo y no llegan al navegador. Su corrección exige cambiar de versión mayor (Vite 8, Tailwind 4) y se programa para la iteración 4, junto con el despliegue de la versión compilada.
* **Fuera del v2 (iteración 4):** comprobante de arqueo en PDF generado por el servidor (RF-10; hoy se imprime desde el navegador), edición de tarifas (RF-11), alerta de demora de limpieza (RF-12), disponibilidad (RNF-06), recuperación al reconectar (RNF-09) y despliegue en AWS.

---

## 9. Declaración de herramientas auxiliares
Conforme al Protocolo de Uso Autorizado de Inteligencia Artificial:

* **Herramienta:** Claude Code, la única herramienta de asistencia que usa el autor. Todos los commits del prototipo se hacen con ella y llevan el trailer `Co-Authored-By: Claude Code`.
* **Uso en el v2:** implementación de la migración 002 y las verificaciones SQL, la autenticación, el servicio de caja y los reportes, las pantallas de ingreso, guardia, cierre de caja y gerencia, las pruebas, los scripts de recorrido y de latencia, y este archivo.
* **Decisiones del autor:** el cierre ciego por guardia, la imputación del cobro a la guardia que atiende, los roles, la separación entre el dueño de las tablas y el rol de la aplicación y las preguntas abiertas para la gerencia.
* **Verificación:** 127 pruebas automáticas (SQLite y PostgreSQL 16), cuatro verificaciones SQL, el recorrido de punta a punta contra la API en Docker, la medición de latencia y una prueba manual en el navegador a 1366 × 768. El detalle por commit (herramienta, función, fecha y verificación) está en la bitácora individual.
