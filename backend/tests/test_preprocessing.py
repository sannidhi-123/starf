import numpy as np
import pandas as pd

from app.modules.dataset.preprocessing import (
    NUMERIC_FEATURES,
    extract_features,
    load_datasets,
    make_sequences,
    split_and_scale_features,
)


def _write_frames(path, rows):
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


def test_dlc_mismatch_is_removed_and_reported(tmp_path):
    path = _write_frames(
        tmp_path / "Normal.txt",
        ["0.0, 123, 2, 01, R", "0.1, 123, 1, FF, R"],
    )

    frames, report = load_datasets(path)

    assert len(frames) == 1
    assert report["rows_in"] == 2
    assert report["rows_out"] == 1
    assert report["removed_per_reason"]["dlc_mismatch"] == 1


def test_duplicate_frames_are_kept(tmp_path):
    duplicate = "0.0, 123, 2, 01, 02, T"
    frames, report = load_datasets(_write_frames(tmp_path / "DoS.txt", [duplicate, duplicate]))

    assert len(frames) == 2
    assert frames["y"].tolist() == [1, 1]
    assert report["removed_per_reason"] == {
        "unparseable": 0,
        "dlc_out_of_range": 0,
        "dlc_mismatch": 0,
        "corrupted": 0,
    }


def test_dt_id_is_computed_per_can_id(tmp_path):
    frames, _ = load_datasets(
        _write_frames(
            tmp_path / "Normal.txt",
            [
                "0.0, 100, 1, 01, R",
                "0.2, 200, 1, 02, R",
                "0.5, 100, 1, 03, R",
            ],
        )
    )

    featured = extract_features(frames)

    assert featured["dt_id"].tolist() == [0.0, 0.0, 0.5]
    assert featured["dt_global"].tolist() == [0.0, 0.2, 0.3]


def test_frequency_uses_one_second_sliding_window(tmp_path):
    frames, _ = load_datasets(
        _write_frames(
            tmp_path / "Normal.txt",
            [
                "0.0, 100, 1, 01, R",
                "0.5, 200, 1, 02, R",
                "1.0, 100, 1, 03, R",
                "1.5, 100, 1, 04, R",
            ],
        )
    )

    featured = extract_features(frames)

    assert featured["freq_global"].tolist() == [1, 2, 3, 3]
    assert featured["freq_id"].tolist() == [1, 1, 2, 2]


def test_scaler_uses_training_rows_only():
    values = np.zeros((10, len(NUMERIC_FEATURES)), dtype=np.float32)
    values[:, 0] = np.arange(10, dtype=np.float32)
    frames = pd.DataFrame(values, columns=NUMERIC_FEATURES)
    frames["y"] = np.zeros(10, dtype=np.uint8)

    split = split_and_scale_features(frames)

    assert split["train_end"] == 7
    assert split["validation_end"] == 8
    assert split["scaler"].mean_[0] == np.mean(np.arange(7))
    assert np.isclose(split["X_train"][:, 0].mean(), 0.0)
    assert split["X_val"][0, 0] > split["X_train"][-1, 0]


def test_make_sequences_returns_strided_views_and_any_attack_labels():
    X = np.arange(24, dtype=np.float32).reshape(8, 3)
    y = np.array([0, 1, 0, 0, 0, 0, 0, 0], dtype=np.uint8)

    sequences, labels = make_sequences(X, y, seq_len=3, stride=2)

    assert sequences.shape == (3, 3, 3)
    assert labels.tolist() == [1, 0, 0]
    assert np.shares_memory(sequences, X)