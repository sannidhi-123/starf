"""Training-only resampling helpers for evaluation scripts."""

from __future__ import annotations

import numpy as np


def prepare_train_validation_test(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    X_test: np.ndarray,
    y_test: np.ndarray,
    *,
    use_smote: bool = False,
    random_state: int = 42,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Optionally resample training data while passing validation/test through unchanged."""
    if len(X_train) != len(y_train):
        raise ValueError("Training features and labels must have the same row count")
    if len(X_val) != len(y_val):
        raise ValueError("Validation features and labels must have the same row count")
    if len(X_test) != len(y_test):
        raise ValueError("Test features and labels must have the same row count")

    if use_smote:
        from imblearn.over_sampling import SMOTE

        X_train, y_train = SMOTE(random_state=random_state).fit_resample(
            X_train, y_train
        )

    return X_train, y_train, X_val, y_val, X_test, y_test
