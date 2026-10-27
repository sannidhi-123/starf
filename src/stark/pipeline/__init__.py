"""stark.pipeline package — end-to-end CAN-frame detection pipeline."""

from __future__ import annotations

from stark.pipeline.features import StreamingFeatures
from stark.pipeline.runner import DetectionPipeline

__all__ = ["DetectionPipeline", "StreamingFeatures"]
