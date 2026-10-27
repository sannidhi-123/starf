"""Pydantic schemas for the ML module (model registry, training, metrics, inference)."""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.modules.detection.schemas import CANFrameInput


class ModelStatus(str, Enum):
    REGISTERED = "registered"
    TRAINING = "training"
    TRAINED = "trained"
    FAILED = "failed"


class Hyperparameters(BaseModel):
    epochs: int = Field(default=300, ge=1, le=5000)
    learning_rate: float = Field(default=0.1, gt=0.0, le=10.0)
    l2: float = Field(default=1e-3, ge=0.0)
    threshold: float = Field(
        default=0.5, gt=0.0, lt=1.0, description="Anomaly score cut-off"
    )
    test_split: float = Field(default=0.2, gt=0.0, lt=0.5)
    seed: int = Field(default=42)


class ModelCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    architecture: str = Field(
        default="baseline-logreg", description="Registered trainer name"
    )
    description: str = Field(default="", max_length=500)
    hyperparameters: Hyperparameters = Field(default_factory=Hyperparameters)


class LabeledFrame(BaseModel):
    frame: CANFrameInput
    label: int = Field(..., ge=0, le=1, description="0 = normal, 1 = attack/anomaly")


class TrainRequest(BaseModel):
    dataset_id: Optional[str] = Field(
        default=None,
        description="Dataset to train on (resolved by the dataset provider)",
    )
    samples: Optional[List[LabeledFrame]] = Field(
        default=None, description="Inline labeled frames, in time order"
    )
    hyperparameters: Optional[Hyperparameters] = Field(
        default=None, description="Overrides the registered values"
    )


class ConfusionMatrix(BaseModel):
    tp: int
    fp: int
    tn: int
    fn: int


class Metrics(BaseModel):
    accuracy: float
    precision: float
    recall: float
    f1: float
    roc_auc: Optional[float] = None
    confusion_matrix: ConfusionMatrix
    train_samples: int
    test_samples: int
    final_loss: float


class ModelRecord(BaseModel):
    id: str
    name: str
    architecture: str
    description: str = ""
    status: ModelStatus = ModelStatus.REGISTERED
    hyperparameters: Hyperparameters = Field(default_factory=Hyperparameters)
    data_source: Optional[str] = Field(
        default=None, description="'inline', 'dataset:<id>' or 'synthetic:<id>'"
    )
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    trained_at: Optional[datetime] = None
    metrics: Optional[Metrics] = None
    artifact: Optional[dict] = Field(
        default=None, description="Serialized trained parameters"
    )

    def public(self) -> "ModelSummary":
        return ModelSummary(
            **self.model_dump(exclude={"artifact", "metrics"}),
            has_metrics=self.metrics is not None,
        )


class ModelSummary(BaseModel):
    id: str
    name: str
    architecture: str
    description: str = ""
    status: ModelStatus
    hyperparameters: Hyperparameters
    data_source: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    trained_at: Optional[datetime] = None
    has_metrics: bool = False


class ModelStatusResponse(BaseModel):
    id: str
    status: ModelStatus
    error: Optional[str] = None
    trained_at: Optional[datetime] = None
    updated_at: datetime


class PredictRequest(BaseModel):
    frames: List[CANFrameInput] = Field(..., min_length=1, max_length=10_000)


class FramePrediction(BaseModel):
    index: int
    can_id: int
    score: float = Field(..., ge=0.0, le=1.0)
    is_anomalous: bool


class PredictResponse(BaseModel):
    model_id: str
    threshold: float
    total: int
    anomalous_count: int
    predictions: List[FramePrediction]
    feature_names: Optional[List[str]] = None


class ModelListResponse(BaseModel):
    items: List[Dict]
