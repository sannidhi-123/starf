"""Optional trained-model inference with an explicitly labeled demo fallback."""

from __future__ import annotations

import random
import os
import pickle
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

CLASSES = ("normal", "dos", "fuzzy", "spoofing")

DOS_PROBS: Dict[str, float] = {
    "dos": 0.93,
    "normal": 0.03,
    "fuzzy": 0.02,
    "spoofing": 0.02,
}

NORMAL_PROBS: Dict[str, float] = {
    "normal": 0.97,
    "dos": 0.01,
    "fuzzy": 0.01,
    "spoofing": 0.01,
}


def _extract_can_id_and_dt(vector: Any) -> Tuple[Optional[int], Optional[float]]:
    """Extract can_id and dt_same_id from a dict or object representation."""
    if isinstance(vector, dict):
        raw_id = vector.get("can_id", vector.get("CAN ID", vector.get("id", None)))
        raw_dt = vector.get("dt_same_id", vector.get("dt", None))
    else:
        raw_id = getattr(
            vector, "can_id", getattr(vector, "CAN ID", getattr(vector, "id", None))
        )
        raw_dt = getattr(vector, "dt_same_id", getattr(vector, "dt", None))

    can_id: Optional[int] = None
    if raw_id is not None:
        if isinstance(raw_id, str):
            v = raw_id.strip()
            try:
                if v.lower().startswith("0x"):
                    can_id = int(v, 16)
                else:
                    can_id = int(v)
            except ValueError:
                try:
                    can_id = int(v, 16)
                except ValueError:
                    can_id = None
        else:
            try:
                can_id = int(raw_id)
            except (ValueError, TypeError):
                can_id = None

    dt_same_id: Optional[float] = None
    if raw_dt is not None:
        try:
            dt_same_id = float(raw_dt)
        except (ValueError, TypeError):
            dt_same_id = None

    return can_id, dt_same_id


class Stage2Model:
    """Load an optional serialized sklearn-compatible estimator.

    ``STARF_ML_MODE`` accepts ``trained``, ``demo`` (default), or ``rules_only``.
    The model artifact is a trusted local pickle produced by ``scripts/train_model.py``.
    """

    def __init__(self, seed: Optional[int] = None, random_mode: bool = False) -> None:
        self.seed = seed
        self.random_mode = random_mode
        self.mode = os.getenv("STARF_ML_MODE", "demo").strip().lower()
        self.artifact_path = Path(
            os.getenv("STARF_MODEL_PATH", "models/starf_model.pkl")
        )
        self.model = None
        self.label_encoder = None
        self.load_error: Optional[str] = None
        if self.mode == "trained":
            try:
                if not self.artifact_path.is_file():
                    raise FileNotFoundError(
                        f"Model artifact not found: {self.artifact_path}"
                    )
                with self.artifact_path.open("rb") as stream:
                    artifact = pickle.load(stream)
                self.model = (
                    artifact.get("model") if isinstance(artifact, dict) else artifact
                )
                self.label_encoder = (
                    artifact.get("label_encoder")
                    if isinstance(artifact, dict)
                    else None
                )
                if self.model is None or not hasattr(self.model, "predict_proba"):
                    raise ValueError(
                        "Model artifact must contain a predict_proba estimator"
                    )
                if isinstance(artifact, dict) and "feature_names" in artifact:
                    from stark.ml.features import FEATURE_NAMES

                    if tuple(artifact["feature_names"]) != FEATURE_NAMES:
                        raise ValueError(
                            "Model feature schema does not match this runtime"
                        )
            except (
                Exception
            ) as exc:  # Optional model failure must not prevent API startup.
                self.load_error = str(exc)
                self.mode = "rules_only"

    def predict(
        self,
        vector: Any,
        seed: Optional[int] = None,
        random_mode: Optional[bool] = None,
    ) -> Tuple[str, Dict[str, float]]:
        """Predict class and class probabilities for input feature vector.

        TEMPORARY STUB - replace with the real model.

        Args:
            vector: Dict or object containing CAN frame features (e.g. can_id, dt_same_id).
            seed: Optional seed override for random mode.
            random_mode: Optional flag to use random mode instead of deterministic rules.

        Returns:
            Tuple of (predicted_class, class_probabilities_dict).
        """
        use_random = random_mode if random_mode is not None else self.random_mode
        active_seed = seed if seed is not None else self.seed

        if use_random:
            rng = random.Random(active_seed)
            raw_scores = [rng.random() + 0.01 for _ in CLASSES]
            total = sum(raw_scores)
            probs = {
                cls_name: score / total for cls_name, score in zip(CLASSES, raw_scores)
            }
            predicted_class = max(probs, key=lambda k: probs[k])
            return predicted_class, probs

        if self.mode == "rules_only":
            return "normal", {"normal": 1.0}

        if self.mode == "trained" and self.model is not None:
            from stark.ml.features import frame_to_vector

            values = frame_to_vector(vector if isinstance(vector, dict) else {})
            raw = self.model.predict_proba([values])[0]
            classes = [str(value).lower() for value in self.model.classes_]
            if self.label_encoder is not None:
                classes = [
                    str(value).lower()
                    for value in self.label_encoder.inverse_transform(
                        self.model.classes_
                    )
                ]
            probs = {name: float(prob) for name, prob in zip(classes, raw)}
            for label in CLASSES:
                probs.setdefault(label, 0.0)
            # Preserve additional classes such as impersonation.
            predicted_class = max(probs, key=probs.get)
            return predicted_class, probs

        can_id, dt_same_id = _extract_can_id_and_dt(vector)

        if can_id == 0 or (dt_same_id is not None and dt_same_id < 0.0005):
            return "dos", dict(DOS_PROBS)
        else:
            return "normal", dict(NORMAL_PROBS)

    def explain(self, vector: Any, predicted_class: str) -> Optional[Dict[str, float]]:
        """Return genuine SHAP contributions for a loaded estimator, if available."""
        if self.model is None:
            return None
        try:
            import numpy as np
            import shap
            from stark.ml.features import FEATURE_NAMES, frame_to_vector

            values = np.asarray(
                [frame_to_vector(vector if isinstance(vector, dict) else {})]
            )
            explanation = shap.TreeExplainer(self.model).shap_values(values)
            if hasattr(explanation, "values"):
                explanation = explanation.values
            class_names = [str(label).lower() for label in self.model.classes_]
            if self.label_encoder is not None:
                class_names = [
                    str(label).lower() for label in self.label_encoder.classes_
                ]
            class_index = class_names.index(predicted_class.lower())
            contributions = (
                explanation[class_index]
                if isinstance(explanation, list)
                else np.asarray(explanation)
            )
            if getattr(contributions, "ndim", 0) == 3:
                contributions = contributions[0, :, class_index]
            else:
                contributions = contributions[0]
            contributions = np.asarray(contributions).reshape(-1)
            return {
                name: float(value) for name, value in zip(FEATURE_NAMES, contributions)
            }
        except Exception:
            return None


def predict(
    vector: Any,
    seed: Optional[int] = None,
    random_mode: bool = False,
) -> Tuple[str, Dict[str, float]]:
    """Functional convenience wrapper for Stage2Model.predict."""
    model = Stage2Model(seed=seed, random_mode=random_mode)
    return model.predict(vector)


def model_status() -> dict[str, Any]:
    """Return honest runtime state for the API and dashboard."""
    model = Stage2Model()
    from stark.ml.features import FEATURE_NAMES

    return {
        "mode": model.mode,
        "available": model.model is not None,
        "model_type": type(model.model).__name__ if model.model is not None else None,
        "artifact_path": str(model.artifact_path),
        "load_error": model.load_error,
        "features": list(FEATURE_NAMES),
    }
