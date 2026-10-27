"""Explicit fallback behavior for the optional Stage 2 model."""

from pathlib import Path

from stark.ml.predict import Stage2Model


def test_demo_mode_is_explicit_and_deterministic(monkeypatch):
    monkeypatch.setenv("STARF_ML_MODE", "demo")
    model = Stage2Model()
    label, probs = model.predict({"can_id": 0, "dt_same_id": 0.01})
    assert model.mode == "demo"
    assert label == "dos"
    assert probs[label] == 0.93
    assert model.explain({}, label) is None


def test_rules_only_mode_does_not_create_model_predictions(monkeypatch):
    monkeypatch.setenv("STARF_ML_MODE", "rules_only")
    model = Stage2Model()
    assert model.predict({"can_id": 0}) == ("normal", {"normal": 1.0})
    assert model.model is None


def test_missing_trained_artifact_falls_back_without_crashing(monkeypatch, tmp_path):
    monkeypatch.setenv("STARF_ML_MODE", "trained")
    monkeypatch.setenv("STARF_MODEL_PATH", str(tmp_path / "missing.pkl"))
    model = Stage2Model()
    assert model.mode == "rules_only"
    assert "not found" in (model.load_error or "")


def test_fixture_runs_through_training_preprocessing():
    # The repository fixture is synthetic and only checks software plumbing;
    # its resulting labels/metrics are not benchmark evidence.
    from scripts.train_model import prepare_xy

    data = Path(__file__).resolve().parents[1] / "data" / "samples" / "fixture.csv"
    vectors, labels = prepare_xy(data)
    assert vectors and len(vectors) == len(labels)
    assert len(vectors[0]) == 8
    assert set(labels) == {"normal", "attack"}
