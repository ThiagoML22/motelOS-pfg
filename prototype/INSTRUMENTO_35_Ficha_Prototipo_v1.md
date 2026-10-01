# UNIVERSIDAD DE LA CUENCA DEL PLATA
### Facultad de Ingeniería, Tecnología y Arquitectura · Ingeniería en Sistemas de Información
### Proyecto Final de Grado · Comisión A · Sede Posadas

---

# INSTRUMENTO 35 · FICHA DEL PROTOTIPO V1
**Momento de aplicación:** Semana 8, antes de crear la etiqueta `v1`.  
**Destino:** Repositorio oficial (`/src` y raíz), junto al archivo de lectura `README.md`, y apartado V.5 del informe.  
**Plazo reglamentario:** Jueves 1.º de octubre de 2026.  
**Proyecto:** Sistema de Procesamiento de Transacciones orientado a Alojamientos transitorios por hora — Caso Motel C.C.  
**Equipo:** Grupo N.º 3 (Thiago Martino Leal & Lautaro Geneyro)  

---

## 35.1 Declaración del Recorrido Vertical

| Estación | Qué se implementó | Archivo o Componente | Qué queda probado |
| :--- | :--- | :--- | :--- |
| **1. Interfaz** | Panel operativo con grilla interactiva de 13 habitaciones, diálogo central por habitación para la apertura de turno, el registro de consumos de minibar y el cobro con confirmación del monto (efectivo, Posnet o Mercado Pago). | `frontend/src/components/RoomsGrid.tsx`<br>`frontend/src/components/RoomCard.tsx`<br>`frontend/src/components/RoomDialog.tsx` | Que la vista sabe emitir comandos transaccionales y renderizar estados reactivos en tiempo real con latencia menor a 500 ms (`RF-01`, `RNF-05`). |
| **2. Lógica de Negocio** | Validación de exclusividad de habitación libre (`RN-EXI-01`), cálculo dinámico de tarifa base y fracciones de sobreturno de 30 minutos (`RN-DER-01`; la tolerancia de 10 minutos y la extracción a un servicio puro quedan planificadas para el Sprint 3), y descuento atómico de inventario (`RN-EXI-02`). | `backend/app/api/v1/endpoints/turnos.py`<br>`backend/app/schemas/turno.py`<br>`backend/app/tests/test_turnos.py` | Que las reglas de negocio se aplican en el backend, verificadas por pruebas automatizadas, y no en la interfaz del cliente. |
| **3. Persistencia** | Modelo relacional en PostgreSQL 16 con políticas de Row-Level Security (RLS) y trigger PL/pgSQL inmutable (`check_turno_inmutable`) que bloquea `UPDATE` y `DELETE` sobre turnos finalizados. | `db/init.sql`<br>`backend/app/models/turno.py`<br>`backend/app/models/habitacion.py` | Que el modelo del dominio se corresponde con un esquema relacional ACID real y que la inmutabilidad de la bitácora transaccional se garantiza a nivel de motor (`RNF-01`). |
| **4. Retorno a la Interfaz** | La confirmación del cierre de turno persiste los pagos, transiciona la habitación a estado «En Limpieza» en la base de datos y refresca inmediatamente la tarjeta en el frontend. | `backend/app/api/v1/endpoints/turnos.py`<br>`frontend/src/App.tsx`<br>`frontend/src/services/api.ts` | Que el circuito transaccional cierra de forma íntegra y consistente de punta a punta. |

---

## Declaraciones del Artefacto

| Campo Declarativo | Detalle Técnico / Definición del Proyecto |
| :--- | :--- |
| **Caso de uso vertical elegido** | **CU-02 (Apertura de Turno) + CU-03 (Despacho de Minibar) + CU-04 (Liquidar y Cobrar Turno con Inmutabilidad)**. |
| **Requisitos del catálogo que implementa** | `RF-01`, `RF-02`, `RF-03`, `RF-04`, `RF-06`, `RF-07`, `RNF-01`, `RNF-02`, `RNF-03`, `RNF-05`. |
| **Reglas de negocio que valida la lógica** | `RN-RES-01` (Inmutabilidad de turnos finalizados), `RN-EXI-01` (Habitación libre para apertura), `RN-EXI-02` (Existencia de stock), `RN-DER-01` (Cálculo de sobreturno por fracciones; tolerancia de 10 minutos pendiente). |
| **Decisión arquitectónica que este recorrido prueba** | Arquitectura desacoplada cliente-servidor (React + FastAPI) con esquema relacional inmutable gobernado por triggers en PostgreSQL 16 para supresión de fraudes y discrepancias de caja. |
| **Alternativas evaluadas y criterio de descarte** | Se evaluó SQLite y MongoDB; se descartaron por carecer de soporte nativo para Row-Level Security (RLS) y triggers robustos de inmutabilidad transaccional requeridos para auditoría financiera. |
| **Etiqueta del repositorio** | `v1` (publicada en rama `main`). |
| **Fecha de la última corrida exitosa del canal CI** | 30 de septiembre de 2026 (corrida de GitHub Actions n.º 36725171762 en verde: 27 tests, `ruff`, `tsc` y build de Vite). Actualizar si se registra una corrida posterior. |

---

## 35.2 Prueba de Clonado en Máquina Limpia

Esta verificación fue realizada por **Lautaro Geneyro** (integrante que no desarrolló el esqueleto de backend), en una computadora independiente sin herramientas ni dependencias preconfiguradas, siguiendo estrictamente el archivo `README.md` sin agregar pasos tácitos:

| # | Paso del Protocolo de Verificación | Resultado Observado | Quién lo verificó y cuándo |
| :---: | :--- | :---: | :--- |
| **1** | Clonado del repositorio en una carpeta nueva: `git clone https://github.com/ThiagoML22/motelOS-pfg.git` | **Satisfactorio** (Clonado completo sin errores de acceso). | Lautaro Geneyro · 29/09/2026 — 17:15 h |
| **2** | Posicionamiento en la etiqueta `v1`: `git checkout v1` | **Satisfactorio** (`HEAD detached at v1`, etiqueta verificada). | Lautaro Geneyro · 29/09/2026 — 17:18 h |
| **3** | Inspección del archivo `README.md` y requisitos previos: Docker Engine y Docker Compose presentes. | **Satisfactorio** (Instrucciones unívocas de instalación). | Lautaro Geneyro · 29/09/2026 — 17:20 h |
| **4** | Configuración de variables: `cp .env.example .env` sin editar credenciales sensibles. | **Satisfactorio** (Variables de entorno completas y funcionales). | Lautaro Geneyro · 29/09/2026 — 17:22 h |
| **5** | Creación del esquema relacional: Verificado a través de `db/init.sql` montado en el contenedor de base de datos. | **Satisfactorio** (Tablas creadas con constraints, RLS y triggers plpgsql). | Lautaro Geneyro · 29/09/2026 — 17:25 h |
| **6** | Arranque de la aplicación: `docker compose up --build -d` | **Satisfactorio** (3 contenedores arriba en menos de 45 segundos). | Lautaro Geneyro · 29/09/2026 — 17:28 h |
| **7** | Ejecución del caso de uso vertical de punta a punta: Ingreso a `localhost:5173`, apertura de Habitación 1 con patente `AA123BB`, agregado de consumición y liquidación con cobro mixto. | **Satisfactorio** (Flujo continuo sin bloqueos, tiempo de respuesta en UI < 500 ms). | Lautaro Geneyro · 29/09/2026 — 17:35 h |
| **8** | Verificación de que el dato persiste y se recupera: Consulta de estado tras recarga de página web e inspección SQL de la tabla `turnos` con trigger inmutable activo. | **Satisfactorio** (Turno finalizado persistido; sentencia de `UPDATE` rechazada por trigger `RN-RES-01`). | Lautaro Geneyro · 29/09/2026 — 17:42 h |
| **9** | Consulta del registro de corridas del canal de construcción: Inspección en GitHub Actions. | **Satisfactorio** (Corrida exitosa con 27 tests unitarios en verde y build de Vite aprobado). | Lautaro Geneyro · 29/09/2026 — 17:45 h |

---

### Constancia Formal de Homologación de Clonado

Se deja constancia formal de que el artefacto de software correspondiente a la etiqueta **`v1`** arranca, compila y ejecuta de manera autónoma y reproducible sobre una máquina limpia, cumpliendo con la totalidad de las condiciones materiales exigidas por la consigna `ISI-PFG-2026C2-AE2-v02`.

* **Firma del Verificador:** Lautaro Geneyro  
* **Firma del Autor del Esqueleto:** Thiago Martino Leal  
* **Fecha:** 29 de septiembre de 2026
