# Motel C.C. — TPS (Sistema de Procesamiento de Transacciones)
### Prototipo v1 · Esqueleto Arquitectónico Ejecutable (Walking Skeleton)

---

## 1. Identificación del Proyecto
* **Denominación del Proyecto:** Sistema de Procesamiento de Transacciones orientado a Alojamientos transitorios por hora — Caso Motel C.C.
* **Asignatura:** Proyecto Final de Grado (Codificación: `ISI-PFG-2026C2-AE2-v02`)
* **Comisión y Sede:** Comisión A · Sede Posadas · Universidad de la Cuenca del Plata
* **Docente Titular:** PosDr. Darío Ezequiel Díaz
* **Autor:** Thiago Martino Leal (proyecto individual)
* **Actividad y Etiqueta:** Actividad de Evaluación N.º 2 (AE2) · Etiqueta Git: `v1`

---

## 2. Qué hace este prototipo
El prototipo v1 implementa el caso de uso vertical completo de **Apertura de Turno, Registro de Consumos, Liquidación Tarifaria y Cierre Inmutable** para el establecimiento Motel C.C. a través de sus cuatro estaciones (Interfaz de usuario $\rightarrow$ Lógica de negocio $\rightarrow$ Persistencia $\rightarrow$ Retorno a la vista). 

Su propósito central no es adelantar volumen de negocio, sino probar deliberadamente la **decisión arquitectónica más comprometida del proyecto**: una arquitectura web desacoplada de baja latencia con backend asíncrono y persistencia transaccional relacional que impone inmutabilidad de datos históricos (Append-Only Log) mediante políticas de Row-Level Security (RLS) y triggers de base de datos a nivel motor, blindando la auditoría de caja frente a adulteraciones o fraudes internos.

---

## 3. Requisitos previos
Para clonar y ejecutar el prototipo en una máquina limpia se requiere contar con:
* **Docker Engine:** Versión $\ge 26.0.0$
* **Docker Compose:** Versión $\ge 2.24.0$
* **Git:** Versión $\ge 2.40$
* *(Opcional para ejecución en entorno local sin contenedores)*:
  * **Python:** Versión exactas `3.12.x`
  * **Node.js:** Versión `20.x` LTS y gestor `npm` $\ge 10.x$
  * **PostgreSQL:** Versión `16.x`

---

## 4. Instalación
Ejecute la siguiente secuencia de comandos en una terminal limpia:

```bash
# 1. Clonar el repositorio oficial
git clone https://github.com/ThiagoML22/motelOS-pfg.git
cd motelOS-pfg

# 2. Posicionarse en la etiqueta v1 correspondiente a la entrega de la AE2
git checkout v1

# 3. Ingresar al directorio del prototipo y crear el archivo de variables de entorno
cd prototype
cp .env.example .env

# 4. Construir las imágenes y levantar los tres contenedores en segundo plano
docker compose up --build -d
```

---

## 5. Configuración de Variables de Entorno
El archivo `.env` se genera a partir de `.env.example` y declara los siguientes parámetros de operación (los valores provistos por defecto son ficticios para entornos de prueba locales y no contienen credenciales sensibles de producción):

| Variable | Descripción y Función Técnica | Valor por Defecto Local |
| :--- | :--- | :--- |
| `POSTGRES_USER` | Nombre del usuario administrador de la base de datos relacional. | `postgres` |
| `POSTGRES_PASSWORD` | Clave de acceso para la instancia local en contenedor Docker. | `postgres` |
| `POSTGRES_DB` | Nombre de la base de datos transaccional del establecimiento. | `motel_db` |
| `DATABASE_URL` | Cadena de conexión asíncrona SQLAlchemy (`asyncpg`) utilizada por el backend. | `postgresql+asyncpg://postgres:postgres@db:5432/motel_db` |
| `VITE_API_URL` | URL base de la API que consume el frontend. | `http://localhost:8000/api/v1` |
| `CORS_ORIGINS` | Lista de orígenes autorizados (separados por coma) para peticiones HTTP cruzadas desde el frontend. | `http://localhost:5173` |
| `SQL_ECHO` | Flag booleano (`True`/`False`) para emitir trazas de sentencias SQL en consola. | `False` |

---

## 6. Ejecución y Verificación del Recorrido Vertical

### A. Direcciones de Servicio
Una vez finalizado el comando `docker compose up --build -d`, los servicios se encontrarán escuchando en:
* **Frontend Web (Consola de Recepción):** [http://localhost:5173](http://localhost:5173)
* **Backend API (Documentación Interactiva Swagger / OpenAPI):** [http://localhost:8000/docs](http://localhost:8000/docs)
* **Base de Datos PostgreSQL 16:** `localhost:5432`

### B. Procedimiento Paso a Paso para Reproducir el Caso de Uso Vertical
Para validar el circuito de extremo a extremo y comprobar que el dato viaja, se aplica la regla de negocio y persiste:

1. **Estación 1 (Interfaz - Visualización del Panel):**
   * Abra un navegador web e ingrese a `http://localhost:5173`.
   * Verifique que se despliega la grilla operativa con las **13 habitaciones** del establecimiento con codificación cromática en tiempo real (satisfaciendo `RF-01` en menos de 500 ms).
2. **Estación 2 (Lógica y Entrada - Apertura de Turno):**
   * Haga clic sobre cualquier habitación en estado **Disponible** (indicador verde, ej. Hab. 01).
   * En el diálogo de apertura, seleccione el tipo de cliente (`Auto`), opcionalmente ingrese una patente vehicular transitoria (ej. `AE987CD`) y presione **Ocupar habitación**. No se registra ningún dato personal del cliente (`RNF-03`).
   * **Resultado observable:** La API FastAPI valida la regla de existencia `RN-EXI-01` (solo habitaciones libres pueden iniciar turno), genera el identificador único transaccional, captura el timestamp automático sin permitir edición manual (`RF-02`) y transiciona la habitación a estado **Ocupada** (indicador azul; el cronómetro pasa a rojo cuando se excede la estadía base) en la interfaz.
3. **Estación 3 (Lógica Transaccional - Despacho de Consumición):**
   * En la tarjeta de la habitación ocupada presione **Agregar producto** (o abra la habitación y use **Agregar productos**).
   * Seleccione la cantidad de un producto del catálogo (ej. "Agua Mineral 500ml") y presione **Guardar en la cuenta**.
   * **Resultado observable:** El backend valida la existencia de inventario (`RN-EXI-02`), descuenta atómicamente el stock del artículo y suma el subtotal al importe adeudado del turno (`RF-04`).
4. **Estación 4 (Persistencia y Retorno - Liquidación y Cierre Inmutable):**
   * En el diálogo de la habitación, presione **Cobrar**.
   * Verifique que el sistema calcula el valor base más los sobreturnos transcurridos según `RN-DER-01` (`RF-03`): 120 minutos de estadía base, 10 minutos de tolerancia y, superada esta, fracciones de 30 minutos (o porción) medidas desde el fin de la estadía base. La liquidación está implementada en `backend/app/services/billing_service.py`.
   * Seleccione el medio de pago (**Efectivo**, **Posnet** o **Mercado Pago**; en los dos últimos se exige el número de comprobante) y presione **Confirmar cobro de $ X**. El sistema liquida el total adeudado vigente (`RF-06`); en esta versión no se admiten cobros parciales ni mixtos.
   * Al confirmar con saldo adeudado en $0, la habitación pasa a estado **En Limpieza** (amarillo) y el turno queda formalmente en estado `FINALIZADO`.
   * **Verificación de Inmutabilidad (`RN-RES-01` / `RNF-01`):** La base de datos activa el trigger `trigger_check_turno_inmutable`. Cualquier intento de modificar (`UPDATE`) o eliminar (`DELETE`) el turno cerrado desde una sentencia SQL será bloqueado a nivel motor emitiendo un error de violación de regla.

---

## 7. Estado del Canal de Construcción (Integración Continua)
El repositorio cuenta con integración continua activa mediante **GitHub Actions**, configurada en el archivo [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) de la raíz del repositorio.

* **Disparador:** Se ejecuta de forma automática ante cada evento de `push` o `pull_request` sobre la rama `main`.
* **Tareas Verificadas en el Backend:**
  1. Entorno de ejecución en contenedor sobre `Python 3.12`.
  2. Servicio de base de datos `PostgreSQL 16` real instanciado durante el pipeline.
  3. Análisis estático de código y formato con **Ruff** (`ruff check app/`).
  4. Suite de **43 pruebas automatizadas con Pytest** (`pytest app/tests/ -v`) que validan formalmente los criterios de aceptación del catálogo.
* **Tareas Verificadas en el Frontend:**
  1. Entorno de compilación sobre `Node.js 20`.
  2. Verificación estricta de tipos con TypeScript (`tsc --noEmit`).
  3. Construcción del bundle estático con **Vite** (`npm run build`).
* **Consulta de Registros:** El historial de corridas en verde se encuentra accesible públicamente en la pestaña **Actions** del repositorio: [https://github.com/ThiagoML22/motelOS-pfg/actions](https://github.com/ThiagoML22/motelOS-pfg/actions).

---

## 8. Limitaciones Conocidas de esta Versión
* **Cobros:** un único pago por turno que cubre el total; no hay pagos parciales ni mixtos.
* **Cierre de caja ciego, autenticación (JWT y roles) e integración con Mercado Pago/POSNET:** previstos para los Sprints 3 y 4. El medio de pago se registra, pero no hay integración con terminales.

---

## 9. Declaración de Herramientas Auxiliares
En estricto cumplimiento del **Protocolo de Uso Autorizado de Inteligencia Artificial** (Apartado 27.2 de la Guía Docente y Apartado 12 de la Consigna AE2):

* **Herramientas empleadas:** Asistentes de generación de código integrados en el entorno de desarrollo (Claude Code / Antigravity).
* **Alcance del uso:** Aceleración del andamiaje arquitectónico inicial (configuración de `docker-compose.yml` y `Dockerfile`, scripts de inicialización de esquema SQL en `db/init.sql`, datos de prueba en `backend/seed.py` y pipeline de GitHub Actions en `ci.yml`) y, en etapas posteriores, la suite de pruebas automatizadas (`backend/app/tests/`), las validaciones de esquemas del backend, el servicio de liquidación temporal y el rediseño de la interfaz del frontend (componentes React y estilos Tailwind).
* **Límites observados:** No se empleó inteligencia artificial generativa para redactar la prosa del informe, los capítulos III, IV, V y X, las bitácoras individuales, ni para justificar decisiones técnicas o de delimitación de alcance. La totalidad de las reglas de negocio, el modelado del dominio y la especificación de requisitos fueron determinados por el autor sobre la base del relevamiento empírico de campo.
* **Control humano:** Todo fragmento de código asistido fue inspeccionado, refactorizado y sometido a pruebas automatizadas de aceptación por el autor antes de su incorporación al repositorio.
