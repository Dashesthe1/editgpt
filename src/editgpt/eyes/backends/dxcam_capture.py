from __future__ import annotations

import time
from collections.abc import Iterator

import numpy as np

from .base import CaptureBackend
from ..types import FramePacket


class DXCamCapture(CaptureBackend):
    """Windows live capture using DXcam 0.1+.

    The normal (non-video-mode) DXcam path blocks until a newly rendered frame
    exists, which keeps EditGPT frame IDs truthful instead of manufacturing
    duplicate observations when the desktop has not changed. DXcam 0.1+ also
    exposes the presentation timestamp supplied by the Windows capture backend.
    """

    def __init__(
        self,
        *,
        monitor_index: int = 0,
        region: tuple[int, int, int, int] | None = None,
        output_color: str = "BGR",
    ) -> None:
        try:
            import dxcam  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "DXcam is not installed. Install editgpt[capture] on Windows."
            ) from exc

        self._monitor_index = monitor_index
        self._region = region
        self._camera = dxcam.create(
            output_idx=monitor_index,
            output_color=output_color,
        )
        self._running = False
        camera_region = tuple(int(v) for v in self._camera.region)
        self._output_region_pixels = camera_region
        self._capture_region_pixels = tuple(int(v) for v in (region or camera_region))

    def frames(self, *, fps: int = 60) -> Iterator[FramePacket]:
        if fps <= 0:
            raise ValueError("fps must be positive")

        self._camera.start(
            region=self._region,
            target_fps=fps,
            video_mode=False,
        )
        self._running = True
        frame_id = 0

        try:
            while self._running:
                try:
                    image, capture_timestamp = self._camera.get_latest_frame(
                        with_timestamp=True
                    )
                except TypeError as exc:
                    raise RuntimeError(
                        "EditGPT requires DXcam 0.1+ for per-frame capture timestamps."
                    ) from exc

                if image is None:
                    continue

                frame_id += 1
                if capture_timestamp is None:
                    timestamp_ns = time.perf_counter_ns()
                else:
                    timestamp_ns = int(float(capture_timestamp) * 1_000_000_000)

                yield FramePacket(
                    frame_id=frame_id,
                    timestamp_ns=timestamp_ns,
                    image=np.array(image, copy=True),
                    source="dxcam",
                    metadata={
                        "capture_timestamp_s": capture_timestamp,
                        "monitor_index": self._monitor_index,
                        "output_region_pixels": list(self._output_region_pixels),
                        "capture_region_pixels": list(self._capture_region_pixels),
                        "coordinate_space": "dxcam_output_pixels",
                    },
                )
        finally:
            self.close()

    def close(self) -> None:
        if self._running:
            self._running = False
            self._camera.stop()
