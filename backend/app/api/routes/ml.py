from functools import lru_cache

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status

from app.core.dependencies import get_integration
from app.integrations.base import Integration
from app.modules.ml import (
    MLService,
    ModelCreate,
    ModelNotFoundError,
    ModelStateError,
    PredictRequest,
    TrainingDataError,
    TrainRequest,
)
from app.modules.ml.schemas import (
    Metrics,
    ModelListResponse,
    ModelStatusResponse,
    ModelSummary,
    PredictResponse,
)

router = APIRouter()


@lru_cache
def get_ml_service() -> MLService:
    return MLService()


def _call(fn, *args):
    """Translate domain errors into HTTP errors."""
    try:
        return fn(*args)
    except ModelNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Model not found")
    except ModelStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except TrainingDataError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))


@router.get("/models", response_model=ModelListResponse)
async def list_models(
    service: MLService = Depends(get_ml_service),
    integration: Integration = Depends(get_integration),
) -> dict:
    items = [m.public().model_dump(mode="json") for m in service.list_models()]
    try:  # externally managed models (mock/real integration); local registry wins on id clashes
        known = {i["id"] for i in items}
        items += [m for m in await integration.list_models() if m["id"] not in known]
    except NotImplementedError:
        pass
    return {"items": items}


@router.post("/models", response_model=ModelSummary, status_code=status.HTTP_201_CREATED)
def register_model(payload: ModelCreate, service: MLService = Depends(get_ml_service)) -> ModelSummary:
    return _call(service.register, payload).public()


@router.get("/models/{model_id}", response_model=ModelSummary)
def get_model(model_id: str, service: MLService = Depends(get_ml_service)) -> ModelSummary:
    return _call(service.get, model_id).public()


@router.delete("/models/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model(model_id: str, service: MLService = Depends(get_ml_service)) -> Response:
    _call(service.delete, model_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/models/{model_id}/train", response_model=ModelSummary, status_code=status.HTTP_202_ACCEPTED)
def train_model(
    model_id: str,
    payload: TrainRequest,
    background: BackgroundTasks,
    service: MLService = Depends(get_ml_service),
) -> ModelSummary:
    record, samples = _call(service.begin_training, model_id, payload)
    background.add_task(service.run_training, model_id, samples)
    return record.public()


@router.get("/models/{model_id}/status", response_model=ModelStatusResponse)
def model_status(model_id: str, service: MLService = Depends(get_ml_service)) -> ModelStatusResponse:
    return _call(service.status, model_id)


@router.get("/models/{model_id}/metrics", response_model=Metrics)
def model_metrics(model_id: str, service: MLService = Depends(get_ml_service)) -> Metrics:
    return _call(service.metrics, model_id)


@router.post("/models/{model_id}/predict", response_model=PredictResponse)
def predict(model_id: str, payload: PredictRequest, service: MLService = Depends(get_ml_service)) -> PredictResponse:
    return _call(service.predict, model_id, payload.frames)
