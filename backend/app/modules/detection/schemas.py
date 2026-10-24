"""Pydantic schemas and domain models for the STARK Detection Pipeline (Stage 1).

Covers CAN frame ingestion, rule configuration, run requests, rule violations,
frame evaluations, and detection summary results as defined in docs/ARCHITECTURE.md.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator


def parse_can_id_value(val: Any) -> int:
    """Parse integer or hexadecimal string representation of a CAN arbitration ID.

    Standard CAN supports 11-bit arbitration IDs (0x000 to 0x7FF, 0 to 2047).
    Extended CAN supports 29-bit arbitration IDs (0x00000000 to 0x1FFFFFFF, 0 to 536870911).
    """
    if isinstance(val, int):
        parsed = val
    elif isinstance(val, str):
        v = val.strip()
        parsed = int(v, 16) if v.lower().startswith("0x") else int(v)
    else:
        raise ValueError(f"Cannot parse CAN ID from value: {val!r}")

    if not (0 <= parsed <= 0x1FFFFFFF):
        raise ValueError(
            f"CAN ID {parsed} (0x{parsed:X}) is outside valid CAN arbitration range (0 to 0x1FFFFFFF)."
        )
    return parsed


# ============================================================================
# Enums
# ============================================================================


class RuleViolationType(str, Enum):
    """Categorization of Stage 1 deterministic rule violations."""

    UNAUTHORIZED_CAN_ID = "unauthorized_can_id"
    DLC_MISMATCH = "dlc_mismatch"
    BURST_RATE = "burst_rate"
    CYCLE_TIMEOUT = "cycle_timeout"
    FREQUENCY_EXCEEDED = "frequency_exceeded"
    PAYLOAD_INVALID = "payload_invalid"
    CUSTOM = "custom"


class ViolationSeverity(str, Enum):
    """Severity ratings for detected rule anomalies."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FrameStatus(str, Enum):
    """Classification status after Stage 1 deterministic filtering."""

    NORMAL = "normal"
    SUSPICIOUS = "suspicious"


class JobStatus(str, Enum):
    """Execution state of a detection run."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# ============================================================================
# CAN Frame Input Model
# ============================================================================


class CANFrameInput(BaseModel):
    """Input representation of a single CAN-Bus frame.

    Compatible with Stage 1 Data Collection & Stage 2 Preprocessing:
    - timestamp: float (epoch or relative timestamp in seconds)
    - can_id: integer or hex string (11-bit standard or 29-bit extended)
    - dlc: integer (payload length code, 0 to 8 bytes for standard CAN)
    - payload: hex string or integer byte sequence (d0 to d7)
    - optional pre-extracted features (delta_t, frequency, byte_entropy)
    """

    timestamp: float = Field(
        ...,
        ge=0.0,
        description="Frame timestamp in seconds (non-negative float)",
    )
    can_id: int = Field(
        ...,
        ge=0,
        le=0x1FFFFFFF,
        description="CAN arbitration ID (supports 11-bit standard or 29-bit extended)",
    )
    dlc: int = Field(
        ...,
        ge=0,
        le=8,
        description="Data Length Code (0 to 8 bytes for standard CAN)",
    )
    payload: str = Field(
        default="",
        description="Payload bytes formatted as normalized hex string (e.g., '00112233')",
    )
    delta_t: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Inter-arrival time difference Δt = t_i - t_{i-1} in seconds",
    )
    frequency: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Message transmission frequency in Hz within a sliding time window",
    )
    byte_entropy: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=8.0,
        description="Shannon entropy of the payload bytes (0.0 to 8.0)",
    )

    @field_validator("can_id", mode="before")
    @classmethod
    def validate_and_parse_can_id(cls, v: Any) -> int:
        return parse_can_id_value(v)

    @field_validator("payload", mode="before")
    @classmethod
    def validate_and_normalize_payload(cls, v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, (list, tuple)):
            for idx, b in enumerate(v):
                if not isinstance(b, int) or not (0 <= b <= 255):
                    raise ValueError(f"Payload byte at index {idx} ({b!r}) must be an integer between 0 and 255")
            return "".join(f"{b:02X}" for b in v)
        if isinstance(v, bytes):
            return v.hex().upper()
        if isinstance(v, str):
            clean = v.replace(" ", "").replace("0x", "").upper()
            if clean and not all(c in "0123456789ABCDEF" for c in clean):
                raise ValueError(f"Invalid characters in hex payload string: {v!r}")
            if len(clean) % 2 != 0:
                raise ValueError(f"Payload hex string must contain an even number of hex digits, got {len(clean)}")
            return clean
        raise ValueError(f"Unsupported payload type {type(v).__name__}. Expected hex string, bytes, or List[int].")

    @model_validator(mode="after")
    def validate_payload_dlc_match(self) -> "CANFrameInput":
        if self.payload:
            payload_bytes_len = len(self.payload) // 2
            if payload_bytes_len != self.dlc:
                raise ValueError(
                    f"Payload byte length ({payload_bytes_len}) does not match DLC ({self.dlc})."
                )
        return self

    @property
    def can_id_hex(self) -> str:
        """Formatted hexadecimal representation of the CAN ID."""
        return f"0x{self.can_id:03X}" if self.can_id <= 0x7FF else f"0x{self.can_id:08X}"

    @property
    def is_extended(self) -> bool:
        """True if the arbitration ID is 29-bit extended (> 0x7FF)."""
        return self.can_id > 0x7FF

    @property
    def payload_bytes(self) -> List[int]:
        """Byte array representation of payload."""
        if not self.payload:
            return []
        return [int(self.payload[i : i + 2], 16) for i in range(0, len(self.payload), 2)]


# ============================================================================
# Detection Rule Configuration
# ============================================================================


class DetectionRuleConfig(BaseModel):
    """Configuration parameters for Stage 1 deterministic rule filtering.

    Enforces:
    - CAN ID Whitelist: flags unauthorized arbitration IDs.
    - DLC compliance: flags frames violating OEM payload length specs.
    - Timing constraints: flags burst transmissions (Δt too small) or timeouts (Δt too large).
    """

    check_id_whitelist: bool = Field(
        default=True,
        description="Whether to validate arbitration IDs against an allowed whitelist",
    )
    allowed_can_ids: Optional[List[int]] = Field(
        default=None,
        description="Whitelist of authorized CAN arbitration IDs. If None, all valid IDs are permitted.",
    )
    enforce_dlc_compliance: bool = Field(
        default=True,
        description="Whether to enforce standard DLC bounds and OEM payload length specs",
    )
    min_dlc: int = Field(
        default=0,
        ge=0,
        le=8,
        description="Minimum permitted DLC (0 to 8)",
    )
    max_dlc: int = Field(
        default=8,
        ge=0,
        le=8,
        description="Maximum permitted DLC (0 to 8)",
    )
    expected_dlc_map: Optional[Dict[int, int]] = Field(
        default=None,
        description="Optional OEM mapping of specific CAN IDs to their exact required DLC",
    )
    enforce_timing_rules: bool = Field(
        default=True,
        description="Whether to enforce timing (delta_t and frequency) constraints",
    )
    min_delta_t: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Minimum inter-arrival time in seconds (threshold below which indicates DoS/flooding bursts)",
    )
    max_delta_t: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Maximum inter-arrival time in seconds (threshold above which indicates transmission timeout)",
    )
    max_frequency_hz: Optional[float] = Field(
        default=None,
        gt=0.0,
        description="Maximum allowable transmission frequency in Hz for any arbitration ID",
    )

    @field_validator("allowed_can_ids", mode="before")
    @classmethod
    def parse_allowed_can_ids(cls, v: Any) -> Optional[List[int]]:
        if v is None:
            return None
        if not isinstance(v, (list, tuple, set)):
            raise ValueError("allowed_can_ids must be an iterable of CAN IDs")
        return [parse_can_id_value(item) for item in v]

    @field_validator("expected_dlc_map", mode="before")
    @classmethod
    def parse_expected_dlc_map(cls, v: Any) -> Optional[Dict[int, int]]:
        if v is None:
            return None
        if not isinstance(v, dict):
            raise ValueError("expected_dlc_map must be a dictionary mapping CAN ID to expected DLC")
        parsed_map: Dict[int, int] = {}
        for k, dlc_val in v.items():
            parsed_id = parse_can_id_value(k)
            if not isinstance(dlc_val, int) or not (0 <= dlc_val <= 8):
                raise ValueError(f"Expected DLC for CAN ID {parsed_id} must be an integer between 0 and 8, got {dlc_val!r}")
            parsed_map[parsed_id] = dlc_val
        return parsed_map

    @model_validator(mode="after")
    def validate_rule_ranges(self) -> "DetectionRuleConfig":
        if self.min_dlc > self.max_dlc:
            raise ValueError(f"min_dlc ({self.min_dlc}) cannot exceed max_dlc ({self.max_dlc}).")
        if self.min_delta_t is not None and self.max_delta_t is not None:
            if self.min_delta_t > self.max_delta_t:
                raise ValueError(f"min_delta_t ({self.min_delta_t}) cannot exceed max_delta_t ({self.max_delta_t}).")
        return self


# ============================================================================
# Detection Run Request
# ============================================================================


class DetectionRunRequest(BaseModel):
    """Payload to trigger a detection job.

    Supports evaluating frames from:
    1. A persistent dataset managed by Dataset Management (via `dataset_id`)
    2. An in-memory batch of CAN frames (via `frames`)
    """

    dataset_id: Optional[str] = Field(
        default=None,
        description="ID of the stored dataset to evaluate (from Dataset Management)",
    )
    frames: Optional[List[CANFrameInput]] = Field(
        default=None,
        description="In-memory list of CAN frames to evaluate directly",
    )
    rule_config: Optional[DetectionRuleConfig] = Field(
        default=None,
        description="Custom rule parameters; uses default deterministic rules if omitted",
    )
    model_id: Optional[str] = Field(
        default=None,
        description="Optional identifier of the Stage 2 ML model to evaluate suspicious frames",
    )
    include_frame_evaluations: bool = Field(
        default=False,
        description="Whether to include detailed per-frame evaluation results in the response",
    )

    @model_validator(mode="after")
    def validate_data_source(self) -> "DetectionRunRequest":
        if not self.dataset_id and not self.frames:
            raise ValueError("Either 'dataset_id' or 'frames' must be provided in DetectionRunRequest.")
        return self


# ============================================================================
# Rule Violation Model
# ============================================================================


class RuleViolation(BaseModel):
    """Detailed record of a single Stage 1 deterministic rule violation."""

    rule_type: Union[RuleViolationType, str] = Field(
        ...,
        description="Category of the violated rule (e.g., 'unauthorized_can_id', 'dlc_mismatch')",
    )
    severity: Union[ViolationSeverity, str] = Field(
        default=ViolationSeverity.MEDIUM,
        description="Severity assessment for this violation (low, medium, high, critical)",
    )
    description: str = Field(
        ...,
        description="Explanatory message detailing the rule violation",
    )
    detected_value: Optional[Any] = Field(
        default=None,
        description="The observed value triggering the rule violation (e.g. invalid DLC or small delta_t)",
    )
    expected_value: Optional[Any] = Field(
        default=None,
        description="The expected reference value or boundary condition",
    )


# ============================================================================
# Frame Evaluation Result
# ============================================================================


class FrameEvaluationResult(BaseModel):
    """Result of Stage 1 deterministic rule evaluation on a single CAN frame.

    Implements the Stage 3 decision point from docs/ARCHITECTURE.md:
    - If compliant -> Normal Traffic (is_suspicious=False, forward_to_ml=False)
    - If rule violation detected -> Suspicious Traffic (is_suspicious=True, forward_to_ml=True)
    """

    frame: CANFrameInput = Field(
        ...,
        description="The evaluated CAN frame",
    )
    status: Union[FrameStatus, str] = Field(
        default=FrameStatus.NORMAL,
        description="Traffic classification: 'normal' or 'suspicious'",
    )
    is_suspicious: bool = Field(
        default=False,
        description="True if any Stage 1 rule violation occurred",
    )
    violations: List[RuleViolation] = Field(
        default_factory=list,
        description="List of detected rule violations (empty for normal frames)",
    )
    forward_to_ml: bool = Field(
        default=False,
        description="True if frame requires Stage 2 Neural Network evaluation",
    )

    @model_validator(mode="after")
    def sync_suspicious_state(self) -> "FrameEvaluationResult":
        if self.violations:
            self.is_suspicious = True
            self.status = FrameStatus.SUSPICIOUS
            self.forward_to_ml = True
        return self


# ============================================================================
# Detection Result / Response
# ============================================================================


class DetectionResponse(BaseModel):
    """Overall response for a detection run.

    Compatible with frontend DetectionJob { job_id, status, matches }
    and the STARK architecture Stage 1 output telemetry.
    """

    job_id: str = Field(
        ...,
        description="Unique identifier for the detection job/run",
    )
    status: Union[JobStatus, str] = Field(
        default=JobStatus.COMPLETED,
        description="Execution status ('queued', 'running', 'completed', 'failed')",
    )
    matches: int = Field(
        default=0,
        ge=0,
        description="Total suspicious matches / violations found (frontend compatible)",
    )
    total_frames: int = Field(
        default=0,
        ge=0,
        description="Total number of CAN frames evaluated",
    )
    normal_count: int = Field(
        default=0,
        ge=0,
        description="Count of normal (compliant) frames",
    )
    suspicious_count: int = Field(
        default=0,
        ge=0,
        description="Count of suspicious frames flagged for Stage 2 ML",
    )
    violations_summary: Dict[str, int] = Field(
        default_factory=dict,
        description="Summary count of violations grouped by rule type",
    )
    frame_evaluations: Optional[List[FrameEvaluationResult]] = Field(
        default=None,
        description="Detailed frame evaluations (included when requested)",
    )
    execution_time_ms: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Detection execution duration in milliseconds",
    )
    dataset_id: Optional[str] = Field(
        default=None,
        description="Source dataset identifier if run against a dataset",
    )

    @model_validator(mode="after")
    def sync_matches_and_counts(self) -> "DetectionResponse":
        if self.suspicious_count > 0 and self.matches == 0:
            self.matches = self.suspicious_count
        elif self.matches > 0 and self.suspicious_count == 0:
            self.suspicious_count = self.matches
        return self


# Alias to satisfy alternate naming conventions
DetectionResultResponse = DetectionResponse
