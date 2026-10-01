# MotelOS · Sistema de Gestión Operativa y Control de Caja para Alojamientos por Turnos

Proyecto Final de Grado de Ingeniería en Sistemas de Información, desarrollado para el establecimiento **Motel C.C.** (Posadas, Misiones). El sistema digitaliza la rotación de habitaciones, aplica la tarifa por tiempo sin intervención discrecional del operador y busca reducir las fugas de dinero mediante un cierre de caja auditable, manteniendo el anonimato de los clientes.

| | |
| :--- | :--- |
| **Institución** | Universidad de la Cuenca del Plata, Sede Posadas |
| **Asignatura** | Proyecto Final de Grado, Comisión A |
| **Autor** | Thiago Martino Leal |
| **Organización cliente** | Motel C.C. |

## Estado del proyecto

| Etapa | Contenido | Estado |
| :--- | :--- | :--- |
| AE1 | Definición del proyecto, relevamiento de campo, investigación de mercado y prototipo de interfaz (v0) | Entregada |
| AE2 | Prototipo v1 ejecutable de punta a punta, con integración continua (etiqueta `v1`) | Publicada |
| Siguiente | Autenticación con roles, cierre de caja ciego e integración con medios de pago | Planificada |

El prototipo v1 cubre el circuito completo de un turno: apertura de habitación, registro de consumos con descuento atómico de stock, liquidación y cobro, y cierre inmutable.

## Estructura del repositorio

```text
.
├── .github/workflows/ci.yml   Integración continua (GitHub Actions)
├── docs/                      Documentación de la AE1: capítulos, anexos y bibliografía
├── portfolio_evidys/          Evidencias del relevamiento de campo
└── prototype/                 Prototipo v1
    ├── backend/               API REST (FastAPI, SQLAlchemy asíncrono)
    ├── frontend/              Aplicación web (React, TypeScript, Tailwind CSS)
    ├── db/                    Esquema PostgreSQL con RLS y trigger de inmutabilidad
    └── docker-compose.yml     Orquestación de los tres servicios
```

## Ejecución del prototipo

Se requiere Docker y Docker Compose. Desde la raíz del repositorio:

```bash
cd prototype
cp .env.example .env
docker compose up --build -d
```

La aplicación queda disponible en `http://localhost:5173` y la documentación interactiva de la API en `http://localhost:8000/docs`. El procedimiento completo para reproducir el caso de uso, la configuración y las limitaciones conocidas están en [`prototype/README.md`](prototype/README.md).

## Reglas de negocio

| Código | Regla | Estado en el prototipo |
| :--- | :--- | :--- |
| RN-EXI-01 | Solo una habitación libre puede iniciar un turno | Implementada |
| RN-EXI-02 | Descuento atómico de stock al registrar un consumo | Implementada |
| RN-EXI-03 | El turno solo se cierra con saldo cero | Implementada para pago único; sin pagos parciales |
| RN-DER-01 | Tarifa base de 120 minutos, tolerancia de 10 minutos y sobreturno por fracciones de 30 minutos | Implementada en un servicio puro del backend |
| RN-RES-01 | Inmutabilidad de los turnos finalizados | Implementada en la base de datos mediante trigger |
| RNF-03 | No se almacenan datos personales de los clientes | Implementada |
| RN-CAJA-01 | Cierre de caja ciego | Pendiente |

## Integración continua

Cada `push` y `pull_request` sobre `main` ejecuta el análisis estático con Ruff, la suite de pruebas del backend sobre PostgreSQL 16, la verificación de tipos de TypeScript y la compilación del frontend. El historial de ejecuciones está en la pestaña [Actions](https://github.com/ThiagoML22/motelOS-pfg/actions) del repositorio.

## Documentación

- [Capítulo I: Definición del proyecto](docs/Capitulo_I_Definicion_del_Proyecto.md): origen, línea de base, objetivos y alcance.
- [Capítulo II: Relevamiento e investigación de mercado](docs/Capitulo_II_Relevamiento_e_Investigacion_de_Mercado.md): entrevista y observación directa, análisis PESTEL, FODA y cinco fuerzas.
- [Anexos y bibliografía](docs/Anexos_y_Bibliografia.md).
- [Informe de la AE1](docs/AE1-LEAL.pdf) (PDF consolidado).
- [Especificación del prototipo v0](prototype/prototipo_v0.md) y [evidencias de campo](portfolio_evidys/relevamiento_campo.md).

## Enlaces

- [Tablero de gestión (Trello)](https://trello.com/invite/b/6a99fdb1fc039c2cb22ed18d/ATTIdb3bba91719943830dd1a31407b21c3f6624A0AA/proyecto-de-grado)
- [Prototipo de interfaz v0 (Figma)](https://www.figma.com/design/KZqjSk1dpEXaXIqSqI5dQL/Prototipo-AE1-Proyecto?node-id=0-1&t=8y8STXw5UH1HEyah-1)
