import pytest
from fastapi.testclient import TestClient

from app.api.routes.ml import get_ml_service
from app.main import app
from app.modules.detection.schemas import CANFrameInput
from app.modules.ml import (
    MLService,
    ModelCreate,
    ModelNotFoundError,
    ModelRegistry,
    ModelStateError,
    ModelStatus,
    TrainingDataError,
    TrainRequest,
)
from app.modules.ml.datasets import SyntheticDatasetProvider
from app.modules.ml.features import frames_to_matrix


@pytest.fixture
def service(tmp_path) -> MLService:
    return MLService(ModelRegistry(tmp_path), SyntheticDatasetProvider(size=600))


@pytest.fixture
def client(service):
    app.dependency_overrides[get_ml_service] = lambda: service
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _trained(service: MLService) -> str:
    rec = service.register(ModelCreate(name="m"))
    _, samples = service.begin_training(rec.id, TrainRequest(dataset_id="demo"))
    service.run_training(rec.id, samples)
    return rec.id


# ---- features ---------------------------------------------------------------
def test_features_derive_delta_t_per_can_id():
    frames = [
        CANFrameInput(timestamp=0.0, can_id=0x100, dlc=1, payload="AA"),
        CANFrameInput(timestamp=0.5, can_id=0x200, dlc=1, payload="BB"),
        CANFrameInput(timestamp=1.0, can_id=0x100, dlc=1, payload="AA"),
    ]
    m = frames_to_matrix(frames)
    assert m.shape == (3, 6)
    assert m[0, 0] != m[0, 0]  # first frame of an ID: delta_t unknown -> NaN
    assert m[2, 0] == pytest.approx(__import__("math").log1p(1000.0))


# ---- service ----------------------------------------------------------------
def test_register_rejects_unknown_architecture(service):
    with pytest.raises(TrainingDataError):
        service.register(ModelCreate(name="x", architecture="nope"))


def test_train_predict_and_metrics(service):
    model_id = _trained(service)
    rec = service.get(model_id)
    assert rec.status == ModelStatus.TRAINED and rec.data_source == "synthetic:demo"
    m = service.metrics(model_id)
    assert m.accuracy > 0.9 and m.recall > 0.8 and m.roc_auc and m.roc_auc > 0.9
    assert m.confusion_matrix.tp + m.confusion_matrix.fn > 0

    flood = CANFrameInput(timestamp=1.0, can_id=0, dlc=8, payload="00" * 8, delta_t=0.0003)
    normal = CANFrameInput(timestamp=2.0, can_id=0x100, dlc=8, payload="0A1B2C3D0A1B2C3D", delta_t=0.01)
    res = service.predict(model_id, [flood, normal])
    assert [p.is_anomalous for p in res.predictions] == [True, False]
    assert res.anomalous_count == 1


def test_state_and_data_errors(service):
    rec = service.register(ModelCreate(name="m"))
    with pytest.raises(ModelStateError):
        service.predict(rec.id, [CANFrameInput(timestamp=0, can_id=1, dlc=0)])
    with pytest.raises(ModelStateError):
        service.metrics(rec.id)
    with pytest.raises(TrainingDataError):
        service.begin_training(rec.id, TrainRequest())
    with pytest.raises(ModelNotFoundError):
        service.get("mdl-missing")
    service.begin_training(rec.id, TrainRequest(dataset_id="d"))
    with pytest.raises(ModelStateError):  # already training
        service.begin_training(rec.id, TrainRequest(dataset_id="d"))
    with pytest.raises(ModelStateError):
        service.delete(rec.id)


def test_interrupted_training_is_recovered_on_restart(tmp_path):
    reg = ModelRegistry(tmp_path)
    svc = MLService(reg, SyntheticDatasetProvider(size=100))
    rec = svc.register(ModelCreate(name="m"))
    svc.begin_training(rec.id, TrainRequest(dataset_id="d"))
    restarted = MLService(reg)
    assert restarted.get(rec.id).status == ModelStatus.FAILED


# ---- API --------------------------------------------------------------------
def test_api_full_workflow(client):
    r = client.post("/api/v1/ml/models", json={"name": "Baseline", "hyperparameters": {"epochs": 200}})
    assert r.status_code == 201
    model_id = r.json()["id"]
    assert r.json()["status"] == "registered"

    assert client.get(f"/api/v1/ml/models/{model_id}/metrics").status_code == 409
    assert client.post(f"/api/v1/ml/models/{model_id}/predict", json={"frames": [
        {"timestamp": 0, "can_id": 1, "dlc": 0}]}).status_code == 409

    r = client.post(f"/api/v1/ml/models/{model_id}/train", json={"dataset_id": "demo"})
    assert r.status_code == 202
    assert client.get(f"/api/v1/ml/models/{model_id}/status").json()["status"] == "trained"  # background task done

    metrics = client.get(f"/api/v1/ml/models/{model_id}/metrics").json()
    assert metrics["f1"] > 0.8

    r = client.post(f"/api/v1/ml/models/{model_id}/predict", json={"frames": [
        {"timestamp": 1.0, "can_id": 0, "dlc": 8, "payload": "0000000000000000", "delta_t": 0.0003}]})
    assert r.status_code == 200 and r.json()["predictions"][0]["is_anomalous"] is True

    assert client.delete(f"/api/v1/ml/models/{model_id}").status_code == 204
    assert client.get(f"/api/v1/ml/models/{model_id}").status_code == 404


def test_api_validation_errors(client):
    assert client.post("/api/v1/ml/models", json={"name": ""}).status_code == 422
    assert client.post("/api/v1/ml/models", json={"name": "x", "architecture": "nope"}).status_code == 422
    model_id = client.post("/api/v1/ml/models", json={"name": "x"}).json()["id"]
    assert client.post(f"/api/v1/ml/models/{model_id}/train", json={}).status_code == 422
    assert client.post("/api/v1/ml/models/mdl-unknown/train", json={"dataset_id": "d"}).status_code == 404
    assert client.get("/api/v1/ml/models/..%2Fetc").status_code == 404


def test_list_models_keeps_mock_integration_items(client):
    client.post("/api/v1/ml/models", json={"name": "Local"})
    items = client.get("/api/v1/ml/models").json()["items"]
    ids = [i["id"] for i in items]
    assert "baseline" in ids  # mock integration still listed
    assert any(i["name"] == "Local" for i in items)
