"""Trainers. Each trainer turns a feature matrix + labels into a JSON-serializable artifact.

`baseline-logreg` is dependency-light (numpy only). Deep models named in docs/ARCHITECTURE.md
(GRU / 1D-CNN / LSTM) can be added by implementing `Trainer` and registering it in `TRAINERS`.
"""

from typing import Protocol

import numpy as np

from app.modules.ml.schemas import ConfusionMatrix, Hyperparameters, Metrics


class Trainer(Protocol):
    name: str

    def fit(
        self, x: np.ndarray, y: np.ndarray, hp: Hyperparameters
    ) -> tuple[dict, float]: ...

    def score(self, artifact: dict, x: np.ndarray) -> np.ndarray: ...


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -40, 40)))


class LogisticRegressionTrainer:
    name = "baseline-logreg"

    def _prepare(
        self, x: np.ndarray, means: np.ndarray, stds: np.ndarray
    ) -> np.ndarray:
        x = np.where(np.isnan(x), means, x)
        return (x - means) / stds

    def fit(
        self, x: np.ndarray, y: np.ndarray, hp: Hyperparameters
    ) -> tuple[dict, float]:
        means = np.nanmean(np.where(np.isfinite(x), x, np.nan), axis=0)
        means = np.where(np.isnan(means), 0.0, means)
        filled = np.where(np.isnan(x), means, x)
        stds = filled.std(axis=0)
        stds = np.where(stds < 1e-9, 1.0, stds)
        z = (filled - means) / stds

        # class-balanced weights so rare attack frames are not ignored
        pos = max(float(y.sum()), 1.0)
        neg = max(float(len(y) - y.sum()), 1.0)
        sw = np.where(y == 1, len(y) / (2 * pos), len(y) / (2 * neg))

        w = np.zeros(z.shape[1])
        b = 0.0
        for _ in range(hp.epochs):
            p = _sigmoid(z @ w + b)
            err = (p - y) * sw
            w -= hp.learning_rate * (z.T @ err / len(y) + hp.l2 * w)
            b -= hp.learning_rate * err.mean()
        p = np.clip(_sigmoid(z @ w + b), 1e-12, 1 - 1e-12)
        loss = float(-(sw * (y * np.log(p) + (1 - y) * np.log(1 - p))).mean())
        artifact = {
            "trainer": self.name,
            "weights": w.tolist(),
            "bias": float(b),
            "means": means.tolist(),
            "stds": stds.tolist(),
        }
        return artifact, loss

    def score(self, artifact: dict, x: np.ndarray) -> np.ndarray:
        z = self._prepare(x, np.array(artifact["means"]), np.array(artifact["stds"]))
        return _sigmoid(z @ np.array(artifact["weights"]) + artifact["bias"])


TRAINERS: dict[str, Trainer] = {
    LogisticRegressionTrainer.name: LogisticRegressionTrainer()
}


def _roc_auc(y: np.ndarray, scores: np.ndarray) -> float | None:
    pos, neg = int(y.sum()), int(len(y) - y.sum())
    if pos == 0 or neg == 0:
        return None
    order = scores.argsort()
    ranks = np.empty(len(scores))
    sorted_scores = scores[order]
    i = 0
    while i < len(scores):  # average ranks for ties
        j = i
        while j + 1 < len(scores) and sorted_scores[j + 1] == sorted_scores[i]:
            j += 1
        ranks[order[i : j + 1]] = (i + j) / 2 + 1
        i = j + 1
    return float((ranks[y == 1].sum() - pos * (pos + 1) / 2) / (pos * neg))


def compute_metrics(
    y: np.ndarray,
    scores: np.ndarray,
    threshold: float,
    train_samples: int,
    final_loss: float,
) -> Metrics:
    pred = (scores >= threshold).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    tn = int(((pred == 0) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return Metrics(
        accuracy=(tp + tn) / max(len(y), 1),
        precision=precision,
        recall=recall,
        f1=f1,
        roc_auc=_roc_auc(y, scores),
        confusion_matrix=ConfusionMatrix(tp=tp, fp=fp, tn=tn, fn=fn),
        train_samples=train_samples,
        test_samples=len(y),
        final_loss=final_loss,
    )
