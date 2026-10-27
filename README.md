# STARK / STARF
**Hybrid Anomaly Detection for Intra-Vehicular CAN-Bus Communication**

> *"Safer Vehicles Through Smarter Detection"*

![STARK Architecture Diagram](docs/assets/stark_architecture.png)

STARK is a hybrid intrusion detection system (IDS) and machine-learning workbench designed to detect cyberattacks and anomalies in intra-vehicular Controller Area Network (CAN-Bus) traffic. It features a two-stage hybrid detection pipeline (deterministic protocol rules + deep neural network classification), a FastAPI backend, and an interactive Vite/React monitoring dashboard.

For detailed design specifications, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).


## Quick start

```bash
cp .env.example .env
docker compose up --build
```

The frontend is available at http://localhost:5173 and the API at
http://localhost:8000. API health and metadata are available at
http://localhost:8000/api/v1/health and http://localhost:8000/docs.

### Local development

From the repository root (recommended so `stark` and sample data are resolved cleanly):

```bash
python -m venv .venv
source .venv/bin/activate  # Or on Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
pip install -e .

# Run the backend with PYTHONPATH pointing to src (or run from repo root):
PYTHONPATH=src uvicorn backend.app.main:app --reload --port 8000
# On Windows PowerShell:
# $env:PYTHONPATH="src"; uvicorn backend.app.main:app --reload --port 8000

cd frontend
npm install
npm run dev
```

Set `INTEGRATION_MODE=real` only after implementing and configuring the real service
adapters. The default `mock` mode keeps the API runnable end-to-end.

### Optional Stage 2 model

Install `backend/requirements-ml.txt`, then train from a labeled CAN CSV with
`python scripts/train_model.py --data path/to/training.csv --model random_forest`.
Set `STARF_ML_MODE=trained` and `STARF_MODEL_PATH=models/starf_model.pkl` to load
the resulting local artifact. `STARF_ML_MODE=demo` uses the clearly labeled
deterministic demo classifier; `STARF_ML_MODE=rules_only` disables Stage 2.
The repository sample files are not verified Car Hacking or OTIDS benchmarks.

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
