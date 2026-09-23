from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["integration"] == "mock"
    assert response.json()["pipeline"] == "hybrid-cascade"


def test_detection_pipeline_uses_fast_path_for_normal_frame() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/detection/frames",
            json={"frames": [{
                "frame_index": 0, "timestamp": 0.0, "can_id": 256,
                "dlc": 3, "data": [1, 2, 3], "source_dataset": "live",
                "capture_id": "test",
            }]},
        )
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["final_class"] == "Normal"
    assert item["decision_path"] == "S1_FAST_PATH"
    assert item["stage2"] is None
