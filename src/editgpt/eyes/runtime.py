from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from .backends.dxcam_capture import DXCamCapture
from .service import EyesService
from .types import FramePacket

CaptureFactory = Callable[..., DXCamCapture]


class LiveEyesRuntime:
    """Owns a persistent live Eyes capture session for MCP/tool callers.

    The runtime deliberately keeps capture state outside individual tool calls so a
    model can start the eye once, inspect multiple moments, and stop it later.
    """

    def __init__(
        self,
        *,
        buffer_capacity: int = 30,
        capture_factory: CaptureFactory = DXCamCapture,
    ) -> None:
        self._default_buffer_capacity = buffer_capacity
        self._capture_factory = capture_factory
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._capture: DXCamCapture | None = None
        self._target_fps = 0
        self._captured_frames = 0
        self._started_ns: int | None = None
        self._first_timestamp_ns: int | None = None
        self._last_timestamp_ns: int | None = None
        self._last_error: str | None = None
        self.service = EyesService(buffer_capacity=buffer_capacity)

    @property
    def running(self) -> bool:
        with self._lock:
            return bool(self._thread and self._thread.is_alive() and not self._stop_event.is_set())

    def start(
        self,
        *,
        fps: int = 60,
        monitor_index: int = 0,
        region: tuple[int, int, int, int] | None = None,
        buffer_seconds: float = 0.5,
    ) -> dict[str, Any]:
        if fps <= 0:
            raise ValueError("fps must be positive")
        if buffer_seconds <= 0:
            raise ValueError("buffer_seconds must be positive")

        with self._lock:
            if self._thread and self._thread.is_alive():
                return {**self.status(), "started": False, "reason": "already_running"}

            capacity = max(2, int(round(fps * buffer_seconds)))
            self.service = EyesService(buffer_capacity=capacity)
            self._capture = self._capture_factory(
                monitor_index=monitor_index,
                region=region,
            )
            self._target_fps = fps
            self._captured_frames = 0
            self._started_ns = time.perf_counter_ns()
            self._first_timestamp_ns = None
            self._last_timestamp_ns = None
            self._last_error = None
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._capture_worker,
                args=(fps,),
                name="editgpt-eyes-capture",
                daemon=True,
            )
            self._thread.start()

        return {**self.status(), "started": True}

    def _capture_worker(self, fps: int) -> None:
        capture = self._capture
        if capture is None:
            return
        try:
            for frame in capture.frames(fps=fps):
                if self._stop_event.is_set():
                    break
                self.service.ingest(frame)
                with self._lock:
                    self._captured_frames += 1
                    if self._first_timestamp_ns is None:
                        self._first_timestamp_ns = frame.timestamp_ns
                    self._last_timestamp_ns = frame.timestamp_ns
        except Exception as exc:  # surface failure through status instead of losing it in a daemon thread
            with self._lock:
                self._last_error = f"{type(exc).__name__}: {exc}"
        finally:
            try:
                capture.close()
            finally:
                self._stop_event.set()

    def stop(self, *, join_timeout_s: float = 2.0) -> dict[str, Any]:
        with self._lock:
            self._stop_event.set()
            capture = self._capture
            thread = self._thread

        if capture is not None:
            capture.close()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=join_timeout_s)

        return {**self.status(), "stopped": True}

    def latest_frame(self) -> FramePacket:
        latest = self.service.buffer.latest(1)
        if not latest:
            raise RuntimeError("no live frame is available; start Eyes and wait for capture")
        return latest[-1]

    def recent_frames(self, *, count: int = 4, stride: int = 1) -> list[FramePacket]:
        if count <= 0:
            raise ValueError("count must be positive")
        if stride <= 0:
            raise ValueError("stride must be positive")
        count = min(count, 8)
        available = self.service.buffer.latest(count * stride)
        if not available:
            return []
        return available[::-stride][:count][::-1]

    def status(self) -> dict[str, Any]:
        with self._lock:
            running = bool(self._thread and self._thread.is_alive() and not self._stop_event.is_set())
            first = self._first_timestamp_ns
            last = self._last_timestamp_ns
            captured = self._captured_frames
            started_ns = self._started_ns
            target_fps = self._target_fps
            last_error = self._last_error

        capture_span_s = 0.0
        observed_fps = 0.0
        if first is not None and last is not None and last >= first:
            capture_span_s = (last - first) / 1_000_000_000
            if capture_span_s > 0 and captured > 1:
                observed_fps = (captured - 1) / capture_span_s

        uptime_s = 0.0 if started_ns is None else max(0.0, (time.perf_counter_ns() - started_ns) / 1_000_000_000)
        return {
            "type": "editgpt_eyes_runtime_status",
            "running": running,
            "target_fps": target_fps,
            "captured_frames": captured,
            "capture_span_s": capture_span_s,
            "observed_fps": observed_fps,
            "uptime_s": uptime_s,
            "last_error": last_error,
            **self.service.health(),
        }
