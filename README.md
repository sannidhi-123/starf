# STARF
STARF implements the STARK architecture: a hybrid intrusion-detection system for
intra-vehicular CAN-bus traffic. The FastAPI backend exposes one shared, label-free
streaming pipeline for live, uploaded, and simulated frames. It computes causal
traffic and payload features, applies a high-recall Stage 1 rule filter, and returns
fail-safe hybrid decisions with severity and evidence. The current Stage 2 is a
deterministic fallback until a verified model artifact is configured.

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

### Detection API

`POST /api/v1/detection/frames` accepts canonical frames (`timestamp`, `can_id`,
`dlc`, and up to eight data bytes) and returns per-frame Stage 1 evidence, Stage 2
output, final class, decision path, severity, and a batch summary. Labels are not
accepted by this inference contract, preserving the architecture's label firewall.

The normal fast path is recorded as `S1_FAST_PATH` and never invokes Stage 2.
Protocol violations and low-confidence decisions remain alert candidates rather
than being silently passed.

## Repository layout

```text
backend/   FastAPI application, integrations, domain modules, and tests
frontend/  Vite React TypeScript application with Tailwind CSS
data/      Local development data mount
docs/      Repository architecture and implementation reference
```

The current implementation map is in [`docs/STARK_ARCHITECTURE.md`](docs/STARK_ARCHITECTURE.md).

## Checks

```bash
python -m compileall backend/app
cd backend && pytest
cd frontend && npm run build
```
