"""The shared, label-free streaming detection pipeline.

Uploads, simulated traffic, and real-time API requests must all enter here.
The implementation is deliberately dependency-light so the prototype can run
before a trained model artifact is available.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from math import log2
from typing import Any

from pydantic import BaseModel, Field, field_validator


class CanonicalFrame(BaseModel):
    frame_index: int = Field(ge=0)
    timestamp: float
    can_id: int = Field(ge=0)
    dlc: int = Field(ge=0)
    data: list[int] = Field(min_length=0, max_length=8)
    source_dataset: str = "live"
    capture_id: str = "stream"

    @field_validator("data")
    @classmethod
    def validate_bytes(cls, value: list[int]) -> list[int]:
        if any(byte < 0 or byte > 255 for byte in value):
            raise ValueError("data bytes must be between 0 and 255")
        return value


class FrameBatch(BaseModel):
    frames: list[CanonicalFrame] = Field(min_length=1, max_length=10_000)


@dataclass
class StreamState:
    recent_ids: deque[int] = field(default_factory=lambda: deque(maxlen=100))
    recent_timestamps: deque[float] = field(default_factory=lambda: deque(maxlen=100))
    last_timestamp_by_id: dict[int, float] = field(default_factory=dict)
    last_payload_by_id: dict[int, list[int]] = field(default_factory=dict)
    consecutive_id: int | None = None
    consecutive_run: int = 0


class DetectionPipeline:
    """Reference implementation of the causal Stage 1 -> Stage 2 cascade."""

    def __init__(self) -> None:
        self.state = StreamState()

    def process(self, frames: list[CanonicalFrame]) -> list[dict[str, Any]]:
        return [self._process_frame(frame) for frame in frames]

    def _process_frame(self, frame: CanonicalFrame) -> dict[str, Any]:
        state = self.state
        previous_timestamp = state.recent_timestamps[-1] if state.recent_timestamps else None
        iat_global = (
            max(0.0, frame.timestamp - previous_timestamp)
            if previous_timestamp is not None
            else 0.0
        )
        previous_id_timestamp = state.last_timestamp_by_id.get(frame.can_id)
        iat_id = (
            max(0.0, frame.timestamp - previous_id_timestamp)
            if previous_id_timestamp is not None
            else 0.0
        )
        id_repetition_count = sum(item == frame.can_id for item in state.recent_ids)
        if state.consecutive_id == frame.can_id:
            state.consecutive_run += 1
        else:
            state.consecutive_id = frame.can_id
            state.consecutive_run = 1

        window_start = frame.timestamp - 1.0
        ids_in_window = [
            item
            for item, timestamp in zip(state.recent_ids, state.recent_timestamps)
            if timestamp >= window_start
        ]
        msg_rate = len(ids_in_window) / 1.0
        id_frequency = sum(item == frame.can_id for item in ids_in_window)
        payload = (frame.data + [0] * 8)[:8]
        previous_payload = state.last_payload_by_id.get(frame.can_id)
        bytes_changed = (
            sum(a != b for a, b in zip(payload, previous_payload))
            if previous_payload is not None
            else 0
        )
        payload_entropy = self._entropy(payload[: frame.dlc])
        features = {
            "can_id": frame.can_id,
            "dlc": frame.dlc,
            "dlc_invalid": frame.dlc > 8,
            "dlc_mismatch": frame.dlc != len(frame.data),
            "iat_global": iat_global,
            "iat_id": iat_id,
            "msg_rate": msg_rate,
            "id_freq": id_frequency,
            "id_share": id_frequency / max(len(ids_in_window), 1),
            "id_repetition_count": id_repetition_count,
            "id_consecutive_run": state.consecutive_run,
            "unique_ids_window": len(set(ids_in_window)),
            "bytes_changed_prev": bytes_changed,
            "payload_entropy": payload_entropy,
        }

        violated: list[str] = []
        hard_violation = False
        if frame.can_id > 0x7FF:
            violated.append("R1_INVALID_CAN_ID")
            hard_violation = True
        if features["dlc_invalid"] or features["dlc_mismatch"]:
            violated.append("R3_INVALID_DLC")
            hard_violation = True
        if msg_rate > 250:
            violated.append("R4_EXCESSIVE_MESSAGE_RATE")
        if id_repetition_count > 80 or state.consecutive_run > 40:
            violated.append("R6_EXCESSIVE_ID_REPETITION")
        if iat_global and iat_global < 0.0001:
            violated.append("R7_TINY_INTER_ARRIVAL")
        if features["unique_ids_window"] > 40:
            violated.append("R8_TRAFFIC_BURST")

        rule_score = float(len(violated)) + (1.0 if hard_violation else 0.0)
        stage1_flag = bool(violated)
        if not stage1_flag:
            final_class = "Normal"
            decision_path = "S1_FAST_PATH"
            alert = False
            confidence = 1.0
            stage2: dict[str, Any] | None = None
        else:
            # Deterministic fallback until a verified model artifact is loaded.
            attack_class = "DoS" if "R4_EXCESSIVE_MESSAGE_RATE" in violated else "Suspicious-Unclassified"
            stage2 = {
                "class": attack_class,
                "confidence": 0.92 if attack_class == "DoS" else 0.55,
                "probabilities": {attack_class: 0.92 if attack_class == "DoS" else 0.55},
                "model_id": "rule-fallback",
            }
            if attack_class == "DoS" and stage2["confidence"] >= 0.8 and not hard_violation:
                final_class, decision_path, confidence = "DoS", "S1_S2_CONFIRMED", stage2["confidence"]
            elif hard_violation:
                final_class, decision_path, confidence = "Suspicious-Unclassified", "HARD_VIOLATION", stage2["confidence"]
            else:
                final_class, decision_path, confidence = "Suspicious-Unclassified", "LOW_CONFIDENCE", stage2["confidence"]
            alert = True

        severity_score = min(100.0, rule_score * 25 + (35 if hard_violation else 0))
        severity = (
            "CRITICAL" if severity_score >= 80 else
            "HIGH" if severity_score >= 60 else
            "MEDIUM" if severity_score >= 30 else
            "LOW" if alert else None
        )
        result = {
            "frame_index": frame.frame_index,
            "timestamp": frame.timestamp,
            "can_id": frame.can_id,
            "stage1": {
                "flag": stage1_flag,
                "violated_rules": violated,
                "rule_score": rule_score,
                "hard_violation": hard_violation,
            },
            "stage2": stage2,
            "final_class": final_class,
            "confidence": confidence,
            "decision_path": decision_path,
            "is_alert_candidate": alert,
            "severity": severity,
            "severity_score": severity_score,
            "features": features,
        }

        state.recent_ids.append(frame.can_id)
        state.recent_timestamps.append(frame.timestamp)
        state.last_timestamp_by_id[frame.can_id] = frame.timestamp
        state.last_payload_by_id[frame.can_id] = payload
        return result

    @staticmethod
    def _entropy(values: list[int]) -> float:
        counts = Counter(values)
        total = len(values)
        return -sum((count / total) * log2(count / total) for count in counts.values()) if total else 0.0
