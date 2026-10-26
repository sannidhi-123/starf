"""File-backed model registry: one JSON document per model under ML_MODEL_DIR (default data/models)."""

import json
import os
import threading
from pathlib import Path
from typing import List

from app.modules.ml.schemas import ModelRecord


class ModelNotFoundError(KeyError):
    pass


class ModelRegistry:
    def __init__(self, directory: str | Path | None = None) -> None:
        self.directory = Path(directory or os.environ.get("ML_MODEL_DIR", "data/models"))
        self._lock = threading.RLock()

    @property
    def lock(self) -> threading.RLock:
        return self._lock

    def _path(self, model_id: str) -> Path:
        if not model_id.replace("-", "").isalnum():
            raise ModelNotFoundError(model_id)
        return self.directory / f"{model_id}.json"

    def save(self, record: ModelRecord) -> None:
        with self._lock:
            self.directory.mkdir(parents=True, exist_ok=True)
            path = self._path(record.id)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(record.model_dump_json(), encoding="utf-8")
            tmp.replace(path)

    def get(self, model_id: str) -> ModelRecord:
        with self._lock:
            path = self._path(model_id)
            if not path.exists():
                raise ModelNotFoundError(model_id)
            return ModelRecord.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def list(self) -> List[ModelRecord]:
        with self._lock:
            if not self.directory.exists():
                return []
            records = [ModelRecord.model_validate_json(p.read_text(encoding="utf-8")) for p in self.directory.glob("*.json")]
        return sorted(records, key=lambda r: r.created_at)

    def delete(self, model_id: str) -> None:
        with self._lock:
            path = self._path(model_id)
            if not path.exists():
                raise ModelNotFoundError(model_id)
            path.unlink()
