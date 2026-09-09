from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np


@dataclass(slots=True, frozen=True)
class FramePacket:
    """One captured/decoded frame plus timing identity.

    `frame_id` is monotonic within one source session. `timestamp_ns` uses a
    monotonic clock for live capture so wall-clock adjustments cannot reorder
    frames.
    """

    frame_id: int
    timestamp_ns: int
    image: np.ndarray = field(repr=False, compare=False)
    source: str = "unknown"
    metadata: Mapping[str, Any] = field(default_factory=dict, compare=False)

    @property
    def shape(self) -> tuple[int, ...]:
        return tuple(self.image.shape)


@dataclass(slots=True, frozen=True)
class MotionObservation:
    frame_id: int
    timestamp_ns: int
    mean_abs_delta: float
    changed_fraction: float
    source: str
