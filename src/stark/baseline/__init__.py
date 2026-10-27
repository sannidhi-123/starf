"""Baseline profiling package for STARK Detection Pipeline (Stage 1).

Extracts per-CAN-ID baseline timing distributions, payload invariants,
and authorized arbitration ID whitelists from benign baseline traffic.
"""

from stark.baseline.profiler import BaselineProfiler

__all__ = ["BaselineProfiler"]
