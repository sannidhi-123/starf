"""Shared schema and dataset normalization tests for Stage 2."""

import pandas as pd
import pytest

from stark.ml.features import FEATURE_NAMES, frame_to_vector, normalize_dataset


def test_normalize_car_hacking_style_columns_and_attack_labels():
    normalized = normalize_dataset(
        pd.DataFrame(
            {
                "Timestamp": ["0.1", "0.2"],
                "CAN ID": ["0140", "0x000"],
                "DLC": ["8", "8"],
                "Flag": ["R", "T"],
            }
        )
    )
    assert normalized["can_id"].tolist() == [320, 0]
    assert normalized["label"].tolist() == ["normal", "attack"]


def test_normalize_rejects_dataset_without_valid_rows():
    with pytest.raises(ValueError, match="No valid rows"):
        normalize_dataset(pd.DataFrame({"timestamp": ["bad"], "can_id": ["xyz"]}))


def test_model_vector_uses_shared_order_and_streaming_aliases():
    vector = frame_to_vector(
        {
            "can_id": 4,
            "can_id_count_50ms": 3,
            "hamming_prev_same_id": 5,
            "id_repetition_count": 2,
        }
    )
    assert len(vector) == len(FEATURE_NAMES)
    assert vector[FEATURE_NAMES.index("can_id_count_50ms")] == 3
    assert vector[FEATURE_NAMES.index("payload_hamming_distance")] == 5
    assert vector[FEATURE_NAMES.index("payload_repeat_streak")] == 2
    assert "id_repetition_count" not in FEATURE_NAMES
