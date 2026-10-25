from __future__ import annotations

from collections import Counter

import numpy as np

from stark.eval.resampling import prepare_train_validation_test


def _counts(labels: np.ndarray) -> dict[int, int]:
    return dict(Counter(map(int, labels)))


def test_smote_changes_training_only_and_preserves_validation_test() -> None:
    X_train = np.arange(400, dtype=np.float32).reshape(100, 4)
    y_train = np.array([0] * 80 + [1] * 20, dtype=np.uint8)
    X_val = np.arange(60, dtype=np.float32).reshape(15, 4)
    y_val = np.array([0] * 10 + [1] * 5, dtype=np.uint8)
    X_test = np.arange(48, dtype=np.float32).reshape(12, 4)
    y_test = np.array([0] * 8 + [1] * 4, dtype=np.uint8)
    validation_before = (X_val.copy(), y_val.copy(), _counts(y_val))
    test_before = (X_test.copy(), y_test.copy(), _counts(y_test))
    training_before = (X_train.copy(), y_train.copy())

    X_resampled, y_resampled, X_val_after, y_val_after, X_test_after, y_test_after = (
        prepare_train_validation_test(
            X_train,
            y_train,
            X_val,
            y_val,
            X_test,
            y_test,
            use_smote=True,
            random_state=42,
        )
    )

    assert len(X_resampled) > len(X_train)
    assert _counts(y_resampled) == {0: 80, 1: 80}
    assert np.array_equal(X_train, training_before[0])
    assert np.array_equal(y_train, training_before[1])
    assert X_val_after.shape[0] == validation_before[0].shape[0]
    assert np.array_equal(X_val_after, validation_before[0])
    assert np.array_equal(y_val_after, validation_before[1])
    assert _counts(y_val_after) == validation_before[2]
    assert X_test_after.shape[0] == test_before[0].shape[0]
    assert np.array_equal(X_test_after, test_before[0])
    assert np.array_equal(y_test_after, test_before[1])
    assert _counts(y_test_after) == test_before[2]
