from __future__ import annotations

from dataclasses import asdict
from typing import Any

import numpy as np

from .buffer import FrameBuffer
from .types import FramePacket, MotionObservation


class EyesService:
    """Backend-neutral visual evidence service for GPT-facing tooling."""

    def __init__(self, *, buffer_capacity: int = 30) -> None:
        self.buffer = FrameBuffer(capacity=buffer_capacity)

    def ingest(self, frame: FramePacket) -> None:
        self.buffer.append(frame)

    def health(self) -> dict[str, Any]:
        latest = self.buffer.latest(1)
        return {
            "ok": True,
            "buffer_size": len(self.buffer),
            "buffer_capacity": self.buffer.capacity,
            "latest_frame_id": latest[-1].frame_id if latest else None,
            "latest_timestamp_ns": latest[-1].timestamp_ns if latest else None,
        }

    def inspect_frames(self, frame_ids: list[int]) -> list[FramePacket]:
        found: list[FramePacket] = []
        for frame_id in frame_ids:
            frame = self.buffer.get(frame_id)
            if frame is not None:
                found.append(frame)
        return found

    def measure_motion(
        self,
        earlier_frame_id: int,
        later_frame_id: int,
        *,
        pixel_threshold: float = 12.0,
    ) -> MotionObservation:
        earlier = self.buffer.get(earlier_frame_id)
        later = self.buffer.get(later_frame_id)
        if earlier is None or later is None:
            raise KeyError("requested frame is no longer available in the buffer")
        if earlier.image.shape != later.image.shape:
            raise ValueError("motion comparison requires frames with identical shapes")

        a = earlier.image.astype(np.float32, copy=False)
        b = later.image.astype(np.float32, copy=False)
        delta = np.abs(b - a)
        if delta.ndim == 3:
            per_pixel = delta.mean(axis=2)
        else:
            per_pixel = delta

        return MotionObservation(
            frame_id=later.frame_id,
            timestamp_ns=later.timestamp_ns,
            mean_abs_delta=float(per_pixel.mean()),
            changed_fraction=float((per_pixel >= pixel_threshold).mean()),
            source=f"{earlier.source}->{later.source}",
        )

    def motion_as_dict(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return asdict(self.measure_motion(*args, **kwargs))
