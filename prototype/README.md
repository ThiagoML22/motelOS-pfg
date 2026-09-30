# Motel C.C. - TPS (Sistema de Procesamiento de Transacciones)

Prototipo del sistema de gestión operativa y control de turnos del Motel C.C.

## Levantar el entorno (Docker)

```bash
cp .env.example .env
docker compose up --build -d
```

- Frontend: http://localhost:5173
- API (Swagger): http://localhost:8000/docs
- PostgreSQL: localhost:5432

## Arquitectura
- **Frontend:** React 18, Vite 5, Tailwind CSS, Axios (TypeScript estricto).
- **Backend:** FastAPI, Pydantic v2, SQLAlchemy asíncrono (asyncpg).
- **Base de datos:** PostgreSQL 16 con RLS y trigger de inmutabilidad de turnos cerrados.

## Verificación local

Backend (Python 3.12):

```bash
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt
ruff check app/ --ignore B008,EXE002
PYTHONPATH=. python -m pytest app/tests/ -v
```

Los tests son herméticos (SQLite en memoria). Para correrlos contra Postgres definir `TEST_DATABASE_URL`
apuntando a una base descartable cuyo nombre contenga `test` (el esquema se recrea en cada test); así corre el CI.

Frontend:

```bash
cd frontend
npm ci
npx tsc --noEmit
npm run build
```

## Variables de entorno
Ver `.env.example`. Opcionales del backend: `SQL_ECHO` (logs SQL) y `CORS_ORIGINS` (lista separada por comas).
