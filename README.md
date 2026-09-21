# STARF
STARF is a dataset detection and machine-learning workbench scaffold. The repository
contains a FastAPI backend and a Vite/React frontend. External services are represented
by interfaces and use deterministic mock implementations by default, so the project can
be run locally without credentials.

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

The frontend is available at http://localhost:5173 and the API at
http://localhost:8000. API health and metadata are available at
http://localhost:8000/api/v1/health and http://localhost:8000/docs.

### Local development

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

cd ../frontend
npm install
npm run dev
```

Set `INTEGRATION_MODE=real` only after implementing and configuring the real service
adapters. The default `mock` mode keeps the API runnable end-to-end.

## Repository layout

```text
backend/   FastAPI application, integrations, domain modules, and tests
frontend/  Vite React TypeScript application with Tailwind CSS
data/      Local development data mount
```

## Checks

```bash
python -m compileall backend/app
cd backend && pytest
cd frontend && npm run build
```
