from __future__ import annotations

from collections import deque
from threading import RLock
from typing import Iterable

from .types import FramePacket


class FrameBuffer:
    """Thread-safe bounded frame history with monotonic identity checks."""

    def __init__(self, capacity: int = 600) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._frames: deque[FramePacket] = deque(maxlen=capacity)
        self._lock = RLock()

    @property
    def capacity(self) -> int:
        return int(self._frames.maxlen or 0)

    def __len__(self) -> int:
        with self._lock:
            return len(self._frames)

    def append(self, frame: FramePacket) -> None:
        with self._lock:
            if self._frames:
                last = self._frames[-1]
                if frame.frame_id <= last.frame_id:
                    raise ValueError("frame_id must increase monotonically")
                if frame.timestamp_ns < last.timestamp_ns:
                    raise ValueError("timestamp_ns must not move backwards")
            self._frames.append(frame)

    def extend(self, frames: Iterable[FramePacket]) -> None:
        for frame in frames:
            self.append(frame)

    def latest(self, count: int = 1) -> list[FramePacket]:
        if count <= 0:
            return []
        with self._lock:
            if count >= len(self._frames):
                return list(self._frames)
            return list(self._frames)[-count:]

    def get(self, frame_id: int) -> FramePacket | None:
        with self._lock:
            for frame in reversed(self._frames):
                if frame.frame_id == frame_id:
                    return frame
                if frame.frame_id < frame_id:
                    break
        return None

    def range(self, start_id: int, end_id: int) -> list[FramePacket]:
        if end_id < start_id:
            raise ValueError("end_id must be >= start_id")
        with self._lock:
            return [f for f in self._frames if start_id <= f.frame_id <= end_id]
