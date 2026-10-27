"""TEMPORARY STUB - replace with the real model.

Stage 2 Machine Learning model inference interface stub.
Deterministic for demo purposes with optional random mode.
"""

from __future__ import annotations

import random
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
        raw_id = getattr(vector, "can_id", getattr(vector, "CAN ID", getattr(vector, "id", None)))
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
    """Stage 2 ML Model inference stub.

    TEMPORARY STUB - replace with the real model.
    """

    def __init__(self, seed: Optional[int] = None, random_mode: bool = False) -> None:
        self.seed = seed
        self.random_mode = random_mode

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
            probs = {cls_name: score / total for cls_name, score in zip(CLASSES, raw_scores)}
            predicted_class = max(probs, key=lambda k: probs[k])
            return predicted_class, probs

        can_id, dt_same_id = _extract_can_id_and_dt(vector)

        if can_id == 0 or (dt_same_id is not None and dt_same_id < 0.0005):
            return "dos", dict(DOS_PROBS)
        else:
            return "normal", dict(NORMAL_PROBS)


def predict(
    vector: Any,
    seed: Optional[int] = None,
    random_mode: bool = False,
) -> Tuple[str, Dict[str, float]]:
    """Functional convenience wrapper for Stage2Model.predict."""
    model = Stage2Model(seed=seed, random_mode=random_mode)
    return model.predict(vector)
