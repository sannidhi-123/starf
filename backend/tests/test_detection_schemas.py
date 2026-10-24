import pytest
from pydantic import ValidationError

from app.modules.detection.schemas import (
    CANFrameInput,
    DetectionResponse,
    DetectionResultResponse,
    DetectionRuleConfig,
    DetectionRunRequest,
    FrameEvaluationResult,
    FrameStatus,
    JobStatus,
    RuleViolation,
    RuleViolationType,
    ViolationSeverity,
)


def test_can_frame_valid_inputs():
    # Standard 11-bit CAN frame with hex string ID and hex payload
    f1 = CANFrameInput(
        timestamp=0.123456,
        can_id="0x1F0",
        dlc=4,
        payload="01 02 03 04",
        delta_t=0.01,
        frequency=100.0,
    )
    assert f1.can_id == 496
    assert f1.can_id_hex == "0x1F0"
    assert not f1.is_extended
    assert f1.payload == "01020304"
    assert f1.payload_bytes == [1, 2, 3, 4]

    # Extended 29-bit CAN frame with integer ID and byte list payload
    f2 = CANFrameInput(
        timestamp=1.5,
        can_id=0x18DAF110,
        dlc=2,
        payload=[0xAA, 0xBB],
    )
    assert f2.is_extended
    assert f2.can_id_hex == "0x18DAF110"
    assert f2.payload == "AABB"
    assert f2.payload_bytes == [0xAA, 0xBB]

    # Zero DLC frame with empty payload
    f3 = CANFrameInput(timestamp=0.0, can_id=0, dlc=0)
    assert f3.dlc == 0
    assert f3.payload == ""
    assert f3.payload_bytes == []


def test_can_frame_validations():
    # Negative timestamp
    with pytest.raises(ValidationError):
        CANFrameInput(timestamp=-1.0, can_id=0x100, dlc=0)

    # CAN ID out of 29-bit range
    with pytest.raises(ValidationError):
        CANFrameInput(timestamp=0.0, can_id=0x20000000, dlc=0)

    # DLC out of 0-8 range
    with pytest.raises(ValidationError):
        CANFrameInput(timestamp=0.0, can_id=0x100, dlc=9)

    # Odd hex payload length
    with pytest.raises(ValidationError):
        CANFrameInput(timestamp=0.0, can_id=0x100, dlc=1, payload="ABC")

    # Invalid hex characters
    with pytest.raises(ValidationError):
        CANFrameInput(timestamp=0.0, can_id=0x100, dlc=1, payload="ZZ")

    # Payload length mismatch with DLC
    with pytest.raises(ValidationError):
        CANFrameInput(timestamp=0.0, can_id=0x100, dlc=4, payload="AABB")


def test_detection_rule_config():
    cfg = DetectionRuleConfig(
        allowed_can_ids=["0x100", 0x1F0, 500],
        min_dlc=1,
        max_dlc=8,
        expected_dlc_map={"0x100": 8, 500: 4},
        min_delta_t=0.001,
        max_delta_t=1.0,
    )
    assert cfg.allowed_can_ids == [256, 496, 500]
    assert cfg.expected_dlc_map[256] == 8
    assert cfg.expected_dlc_map[500] == 4

    # min_dlc > max_dlc should raise ValidationError
    with pytest.raises(ValidationError):
        DetectionRuleConfig(min_dlc=6, max_dlc=2)

    # min_delta_t > max_delta_t should raise ValidationError
    with pytest.raises(ValidationError):
        DetectionRuleConfig(min_delta_t=1.5, max_delta_t=0.5)


def test_detection_run_request():
    # Valid with dataset_id
    req1 = DetectionRunRequest(dataset_id="car-hacking-dos")
    assert req1.dataset_id == "car-hacking-dos"

    # Valid with in-memory frames
    frame = CANFrameInput(timestamp=0.0, can_id=0x123, dlc=0)
    req2 = DetectionRunRequest(frames=[frame])
    assert len(req2.frames) == 1

    # Invalid when neither is provided
    with pytest.raises(ValidationError):
        DetectionRunRequest()


def test_rule_violation_and_frame_evaluation():
    frame = CANFrameInput(timestamp=1.0, can_id=0x7FF, dlc=0)

    # Compliant normal frame
    eval_normal = FrameEvaluationResult(frame=frame)
    assert not eval_normal.is_suspicious
    assert eval_normal.status == FrameStatus.NORMAL
    assert not eval_normal.forward_to_ml
    assert len(eval_normal.violations) == 0

    # Suspicious frame with violation
    violation = RuleViolation(
        rule_type=RuleViolationType.BURST_RATE,
        severity=ViolationSeverity.HIGH,
        description="Inter-arrival time Δt below threshold (0.0001s < 0.005s)",
        detected_value=0.0001,
        expected_value=0.005,
    )
    eval_suspicious = FrameEvaluationResult(frame=frame, violations=[violation])
    assert eval_suspicious.is_suspicious
    assert eval_suspicious.status == FrameStatus.SUSPICIOUS
    assert eval_suspicious.forward_to_ml


def test_detection_response():
    resp = DetectionResponse(
        job_id="job-1234",
        status=JobStatus.COMPLETED,
        total_frames=100,
        normal_count=95,
        suspicious_count=5,
        violations_summary={"burst_rate": 5},
    )
    # matches should sync with suspicious_count
    assert resp.matches == 5
    assert resp.job_id == "job-1234"
    assert resp.status == JobStatus.COMPLETED

    # Verify alias
    assert DetectionResultResponse is DetectionResponse
