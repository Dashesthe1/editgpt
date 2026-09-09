from __future__ import annotations

import time

import numpy as np

from editgpt.eyes.runtime import LiveEyesRuntime
from editgpt.eyes.types import FramePacket


class FakeCapture:
    def __init__(self, **_: object) -> None:
        self.closed = False

    def frames(self, *, fps: int = 60):
        step_ns = int(1_000_000_000 / fps)
        for index in range(1, 6):
            if self.closed:
                break
            yield FramePacket(
                frame_id=index,
                timestamp_ns=index * step_ns,
                image=np.full((8, 8, 3), index, dtype=np.uint8),
                source="fake",
                metadata={},
            )

    def close(self) -> None:
        self.closed = True


def test_runtime_retains_recent_frames_and_reports_rate() -> None:
    runtime = LiveEyesRuntime(buffer_capacity=3, capture_factory=FakeCapture)
    started = runtime.start(fps=60, buffer_seconds=0.05)
    assert started["started"] is True

    deadline = time.perf_counter() + 1.0
    while time.perf_counter() < deadline:
        status = runtime.status()
        if status["captured_frames"] >= 5:
            break
        time.sleep(0.01)

    status = runtime.status()
    assert status["captured_frames"] == 5
    assert status["observed_fps"] > 59.0
    assert runtime.latest_frame().frame_id == 5
    assert [frame.frame_id for frame in runtime.recent_frames(count=2)] == [4, 5]
