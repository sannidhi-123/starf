"""Streaming (causal) per-run feature extractor for CAN frames.

Computes causal derived features required by the Stage 1 RuleEngine and Stage 2 using only
information available at the time each frame arrives — no look-ahead.  State is
reset via :meth:`reset` between runs.
"""

from __future__ import annotations

import collections
import math
from typing import Any, Dict, List, Optional

from stark.rules.definitions import (
    FEATURE_CAN_ID,
    FEATURE_DELTA_T,
    FEATURE_DLC,
    FEATURE_HAMMING_DISTANCE,
    FEATURE_MSG_RATE_50MS,
    FEATURE_REPETITION_COUNT,
)

# Sliding-window widths in seconds. The ID count is a separate signal from the
# existing consecutive-identical-payload counter used by R5.
_WINDOW_SEC: float = 0.050
_ID_COUNT_WINDOW_SEC: float = 0.050


def _parse_can_id(val: Any) -> int:
    """Parse CAN ID from int or hex string to int."""
    if isinstance(val, int):
        return int(val)
    s = str(val).strip()
    if s.lower().startswith("0x"):
        return int(s, 16)
    try:
        return int(s, 16)
    except ValueError:
        return int(s)


def _payload_bytes(payload_val: Any) -> bytes:
    """Convert a payload value to bytes.

    Accepts:
    * ``bytes`` / ``bytearray``
    * hex string (with or without spaces / ``0x`` prefix), e.g. ``"AABB"``
    * list/tuple of integers
    * ``None`` or empty string → b""
    """
    if payload_val is None:
        return b""
    if isinstance(payload_val, (bytes, bytearray)):
        return bytes(payload_val)
    if isinstance(payload_val, (list, tuple)):
        return bytes(int(b) & 0xFF for b in payload_val if b is not None)
    s = str(payload_val).replace(" ", "").replace("0x", "").strip()
    if not s:
        return b""
    try:
        return bytes.fromhex(s)
    except ValueError:
        return s.encode("utf-8")


def _hamming(b1: bytes, b2: bytes) -> int:
    """Bitwise Hamming distance between two byte payloads."""
    common = min(len(b1), len(b2))
    dist = sum((x ^ y).bit_count() for x, y in zip(b1[:common], b2[:common]))
    dist += abs(len(b1) - len(b2)) * 8
    return dist


class StreamingFeatures:
    """Causal, per-run streaming feature extractor.

    Maintains state across frames in a single run.  Call :meth:`reset` before
    each new run to clear all per-ID history and the bus-wide sliding window.

    Usage::

        sf = StreamingFeatures()
        for raw_frame in frames:
            enriched = sf.update(raw_frame)
            verdict = engine.evaluate(enriched)
    """

    def __init__(self, id_count_window_sec: float = _ID_COUNT_WINDOW_SEC) -> None:
        if id_count_window_sec <= 0:
            raise ValueError("id_count_window_sec must be positive")
        self.id_count_window_sec = float(id_count_window_sec)
        self.reset()

    def reset(self) -> None:
        """Clear all causal state.  Must be called at the start of each run."""
        # Per-ID: last seen timestamp (seconds)
        self._last_seen_time: Dict[int, float] = {}
        # Per-ID: last payload bytes
        self._last_payload: Dict[int, bytes] = {}
        # Per-ID: consecutive identical payload run-length counter
        self._rep_counts: Dict[int, int] = {}
        # Bus-wide sliding window of timestamps for msg_rate_50ms
        self._window_ts: collections.deque[float] = collections.deque()
        # CAN ID occurrence history for the causal ID Repetition Count.
        self._id_window: collections.deque[tuple[float, int]] = collections.deque()
        self._last_timestamp: Optional[float] = None

    def update(self, frame: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich *frame* with the four derived features and return the enriched dict.

        The input dict is not mutated; a shallow copy with added keys is returned.

        Keys consumed from *frame*:
        - ``"can_id"`` or ``"CAN ID"`` (int or hex str)
        - ``"timestamp"`` or ``"Timestamp"`` (float, optional but needed for dt/rate)
        - ``"dlc"`` or ``"DLC"`` (int, forwarded as-is)
        - ``"payload"`` (hex str, optional, used for repetition / Hamming)
        - Per-column bytes: ``"DATA[0]"`` … ``"DATA[7]"`` (fallback for payload)

        Keys added / overwritten in the result dict (exact names from definitions.py):
        - ``"can_id"`` (int)
        - ``"dlc"`` (int)
        - ``"dt_same_id"`` (float | None)
        - ``"msg_rate_50ms"`` (int)
        - ``"id_repetition_count"`` (int)
        - ``"hamming_prev_same_id"`` (int | None)
        """
        # ------------------------------------------------------------------ #
        # 0. Parse base fields
        # ------------------------------------------------------------------ #
        _MISSING = object()
        raw_id = frame.get("can_id", frame.get("CAN ID", frame.get("id", 0)))
        can_id: int = _parse_can_id(raw_id)

        raw_dlc = frame.get("dlc", frame.get("DLC", 0))
        dlc: int = int(raw_dlc) if raw_dlc is not None else 0

        ts_raw = frame.get(
            "timestamp", frame.get("Timestamp", frame.get("ts", _MISSING))
        )
        timestamp: Optional[float] = None
        if ts_raw is not _MISSING and ts_raw is not None:
            try:
                _f_val = float(ts_raw)
                if math.isfinite(_f_val):
                    timestamp = _f_val
            except (ValueError, TypeError):
                timestamp = None

        # ------------------------------------------------------------------ #
        # 1. Extract payload bytes (for R5/R6 features)
        # ------------------------------------------------------------------ #
        payload_raw = frame.get("payload", frame.get("Payload", None))
        if payload_raw is not None:
            p_bytes = _payload_bytes(payload_raw)
        else:
            # Fallback: read DATA[0..7] columns
            byte_vals: List[int] = []
            for i in range(8):
                v = (
                    frame.get(f"DATA[{i}]")
                    or frame.get(f"data_{i}")
                    or frame.get(f"d{i}")
                )
                if v is not None and str(v).strip():
                    try:
                        byte_vals.append(int(str(v).strip(), 16) & 0xFF)
                    except ValueError:
                        try:
                            byte_vals.append(int(str(v).strip()) & 0xFF)
                        except ValueError:
                            pass
            p_bytes = bytes(byte_vals)

        # ------------------------------------------------------------------ #
        # 2. dt_same_id — seconds since previous frame with the same CAN ID
        # ------------------------------------------------------------------ #
        dt_same_id: Optional[float] = None
        if timestamp is not None:
            # Out-of-order observations do not rewind any causal state.
            in_order = self._last_timestamp is None or timestamp >= self._last_timestamp
            if in_order and can_id in self._last_seen_time:
                dt_same_id = timestamp - self._last_seen_time[can_id]
            if in_order:
                self._last_seen_time[can_id] = timestamp
                self._last_timestamp = timestamp

        # ------------------------------------------------------------------ #
        # 3. msg_rate_50ms — bus-wide frame count in the trailing 50 ms window
        # ------------------------------------------------------------------ #
        msg_rate_50ms: int = 0
        if timestamp is not None and (
            self._last_timestamp is None or timestamp >= self._last_timestamp
        ):
            self._window_ts.append(timestamp)
            cutoff = timestamp - _WINDOW_SEC
            while self._window_ts and self._window_ts[0] < cutoff:
                self._window_ts.popleft()
            msg_rate_50ms = len(self._window_ts)

        # ------------------------------------------------------------------ #
        # 4. id_repetition_count — consecutive identical payloads for this ID
        # ------------------------------------------------------------------ #
        if can_id in self._last_payload and self._last_payload[can_id] == p_bytes:
            self._rep_counts[can_id] = self._rep_counts.get(can_id, 1) + 1
        else:
            self._rep_counts[can_id] = 1
        id_repetition_count: int = self._rep_counts[can_id]

        # Count this ID's frames in the trailing, inclusive window using only
        # this frame and observations already seen. Invalid/out-of-order times
        # produce 0 and leave the history untouched.
        can_id_count_window = 0
        if timestamp is not None and (
            not self._id_window or timestamp >= self._id_window[-1][0]
        ):
            cutoff = timestamp - self.id_count_window_sec
            while self._id_window and self._id_window[0][0] < cutoff:
                self._id_window.popleft()
            self._id_window.append((timestamp, can_id))
            can_id_count_window = sum(cid == can_id for _, cid in self._id_window)

        # ------------------------------------------------------------------ #
        # 5. hamming_prev_same_id — bit distance to previous payload of same ID
        # ------------------------------------------------------------------ #
        hamming_prev_same_id: Optional[int] = None
        if can_id in self._last_payload:
            hamming_prev_same_id = _hamming(p_bytes, self._last_payload[can_id])

        self._last_payload[can_id] = p_bytes

        byte_entropy = 0.0
        if p_bytes:
            counts = collections.Counter(p_bytes)
            byte_entropy = -sum(
                (count / len(p_bytes)) * math.log2(count / len(p_bytes))
                for count in counts.values()
            )

        # ------------------------------------------------------------------ #
        # 6. Return enriched frame dict
        # ------------------------------------------------------------------ #
        result: Dict[str, Any] = dict(frame)  # shallow copy
        result[FEATURE_CAN_ID] = can_id
        result[FEATURE_DLC] = dlc
        result[FEATURE_DELTA_T] = dt_same_id
        result[FEATURE_MSG_RATE_50MS] = msg_rate_50ms
        result[FEATURE_REPETITION_COUNT] = id_repetition_count
        result["can_id_count_50ms"] = can_id_count_window
        result[FEATURE_HAMMING_DISTANCE] = hamming_prev_same_id
        result["payload_hamming_distance"] = hamming_prev_same_id
        result["byte_entropy"] = byte_entropy
        return result
