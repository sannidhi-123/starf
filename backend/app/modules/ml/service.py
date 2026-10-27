import uuid
from datetime import datetime, timezone
from typing import List, Optional

import numpy as np

from app.modules.detection.schemas import CANFrameInput
from app.modules.ml.datasets import DatasetProvider, SyntheticDatasetProvider
from app.modules.ml.features import FEATURE_NAMES, frames_to_matrix
from app.modules.ml.registry import ModelNotFoundError, ModelRegistry
from app.modules.ml.schemas import (
    FramePrediction,
    LabeledFrame,
    Metrics,
    ModelCreate,
    ModelRecord,
    ModelStatus,
    ModelStatusResponse,
    PredictResponse,
    TrainRequest,
)
from app.modules.ml.trainer import TRAINERS, compute_metrics

MIN_TRAIN_SAMPLES = 20


class ModelStateError(Exception):
    """Operation not allowed in the model's current status (HTTP 409)."""


class TrainingDataError(ValueError):
    """Training input is missing or unusable (HTTP 422)."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


class MLService:
    """Model registration, training/inference workflow, status and metrics."""

    def __init__(self, registry: Optional[ModelRegistry] = None, dataset_provider: Optional[DatasetProvider] = None) -> None:
        self.registry = registry or ModelRegistry()
        self.dataset_provider = dataset_provider or SyntheticDatasetProvider()
        self._recover_interrupted()

    def _recover_interrupted(self) -> None:
        for rec in self.registry.list():
            if rec.status == ModelStatus.TRAINING:
                rec.status, rec.error, rec.updated_at = ModelStatus.FAILED, "Training interrupted by restart", _now()
                self.registry.save(rec)

    # ---- registration / lookup -------------------------------------------------
    def register(self, payload: ModelCreate) -> ModelRecord:
        if payload.architecture not in TRAINERS:
            raise TrainingDataError(f"Unknown architecture '{payload.architecture}'. Available: {sorted(TRAINERS)}")
        now = _now()
        record = ModelRecord(
            id=f"mdl-{uuid.uuid4().hex[:12]}",
            created_at=now,
            updated_at=now,
            **payload.model_dump(),
        )
        self.registry.save(record)
        return record

    def list_models(self) -> List[ModelRecord]:
        return self.registry.list()

    def get(self, model_id: str) -> ModelRecord:
        return self.registry.get(model_id)

    def delete(self, model_id: str) -> None:
        with self.registry.lock:
            if self.registry.get(model_id).status == ModelStatus.TRAINING:
                raise ModelStateError("Cannot delete a model while it is training")
            self.registry.delete(model_id)

    def status(self, model_id: str) -> ModelStatusResponse:
        r = self.registry.get(model_id)
        return ModelStatusResponse(id=r.id, status=r.status, error=r.error, trained_at=r.trained_at, updated_at=r.updated_at)

    def metrics(self, model_id: str) -> Metrics:
        r = self.registry.get(model_id)
        if r.metrics is None:
            raise ModelStateError(f"Model is '{r.status.value}'; metrics are available after training completes")
        return r.metrics

    # ---- training --------------------------------------------------------------
    def begin_training(self, model_id: str, req: TrainRequest) -> tuple[ModelRecord, List[LabeledFrame]]:
        """Validate input and mark the model as training. Call `run_training` with the returned samples."""
        if req.samples:
            samples, source = req.samples, "inline"
        elif req.dataset_id:
            samples = self.dataset_provider.load(req.dataset_id)
            source = f"{self.dataset_provider.source}:{req.dataset_id}"
        else:
            raise TrainingDataError("Provide 'dataset_id' or 'samples' to train a model")
        labels = {s.label for s in samples}
        if len(samples) < MIN_TRAIN_SAMPLES or labels != {0, 1}:
            raise TrainingDataError(
                f"Need at least {MIN_TRAIN_SAMPLES} samples containing both normal (0) and attack (1) labels"
            )
        with self.registry.lock:
            record = self.registry.get(model_id)
            if record.status == ModelStatus.TRAINING:
                raise ModelStateError("Model is already training")
            if req.hyperparameters:
                record.hyperparameters = req.hyperparameters
            record.status, record.error, record.data_source, record.updated_at = ModelStatus.TRAINING, None, source, _now()
            self.registry.save(record)
        return record, list(samples)

    def run_training(self, model_id: str, samples: List[LabeledFrame]) -> ModelRecord:
        record = self.registry.get(model_id)
        try:
            hp = record.hyperparameters
            x = frames_to_matrix([s.frame for s in samples])
            y = np.array([s.label for s in samples], dtype=float)
            order = np.random.default_rng(hp.seed).permutation(len(y))
            n_test = max(int(len(y) * hp.test_split), 1)
            test_idx, train_idx = order[:n_test], order[n_test:]
            if len(set(y[train_idx])) < 2:
                raise TrainingDataError("Training split contains a single class; provide more varied data")
            trainer = TRAINERS[record.architecture]
            artifact, loss = trainer.fit(x[train_idx], y[train_idx], hp)
            artifact["feature_names"] = FEATURE_NAMES
            scores = trainer.score(artifact, x[test_idx])
            record.metrics = compute_metrics(y[test_idx], scores, hp.threshold, len(train_idx), loss)
            record.artifact, record.status, record.trained_at = artifact, ModelStatus.TRAINED, _now()
        except Exception as exc:  # surfaced through the status endpoint
            record.status, record.error = ModelStatus.FAILED, str(exc)
        record.updated_at = _now()
        self.registry.save(record)
        return record

    # ---- inference -------------------------------------------------------------
    def predict(self, model_id: str, frames: List[CANFrameInput]) -> PredictResponse:
        record = self.registry.get(model_id)
        if record.status != ModelStatus.TRAINED or record.artifact is None:
            raise ModelStateError(f"Model is '{record.status.value}'; train it before running inference")
        scores = TRAINERS[record.architecture].score(record.artifact, frames_to_matrix(frames))
        threshold = record.hyperparameters.threshold
        predictions = [
            FramePrediction(index=i, can_id=f.can_id, score=float(s), is_anomalous=bool(s >= threshold))
            for i, (f, s) in enumerate(zip(frames, scores))
        ]
        return PredictResponse(
            model_id=record.id,
            threshold=threshold,
            total=len(predictions),
            anomalous_count=sum(p.is_anomalous for p in predictions),
            predictions=predictions,
            feature_names=record.artifact.get("feature_names"),
        )


__all__ = ["MLService", "ModelNotFoundError", "ModelStateError", "TrainingDataError"]
