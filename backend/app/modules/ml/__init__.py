"""Machine-learning model module (Stage 2: model registry, training, metrics, inference)."""

from app.modules.ml.registry import ModelNotFoundError, ModelRegistry
from app.modules.ml.schemas import (
    FramePrediction,
    Hyperparameters,
    LabeledFrame,
    Metrics,
    ModelCreate,
    ModelRecord,
    ModelStatus,
    PredictRequest,
    PredictResponse,
    TrainRequest,
)
from app.modules.ml.service import MLService, ModelStateError, TrainingDataError

__all__ = [
    "FramePrediction",
    "Hyperparameters",
    "LabeledFrame",
    "Metrics",
    "MLService",
    "ModelCreate",
    "ModelNotFoundError",
    "ModelRecord",
    "ModelRegistry",
    "ModelStateError",
    "ModelStatus",
    "PredictRequest",
    "PredictResponse",
    "TrainRequest",
    "TrainingDataError",
]
