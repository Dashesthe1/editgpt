from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .eyes.backends.dxcam_capture import DXCamCapture
from .eyes.service import EyesService


def _capture(seconds: float, fps: int, buffer_seconds: float, save_dir: str | None) -> int:
    capacity = max(2, int(fps * buffer_seconds))
    service = EyesService(buffer_capacity=capacity)
    capture = DXCamCapture()
    deadline = time.perf_counter() + seconds
    started = time.perf_counter()
    previous_id: int | None = None
    first_timestamp_ns: int | None = None
    last_timestamp_ns: int | None = None
    frame_count = 0
    changed_sum = 0.0
    motion_count = 0
    next_sample_at = 0.0
    sample_index = 0

    output = Path(save_dir) if save_dir else None
    if output:
        output.mkdir(parents=True, exist_ok=True)
        try:
            import cv2  # type: ignore
        except ImportError as exc:
            raise RuntimeError("Saving proof frames requires OpenCV.") from exc
    else:
        cv2 = None

    try:
        for frame in capture.frames(fps=fps):
            service.ingest(frame)
            frame_count += 1
            if first_timestamp_ns is None:
                first_timestamp_ns = frame.timestamp_ns
            last_timestamp_ns = frame.timestamp_ns

            elapsed = time.perf_counter() - started
            if output and elapsed >= next_sample_at:
                cv2.imwrite(str(output / f"sample_{sample_index:03d}.jpg"), frame.image)
                sample_index += 1
                next_sample_at += 1.0

            if previous_id is not None and service.buffer.get(previous_id) is not None:
                motion = service.measure_motion(previous_id, frame.frame_id)
                changed_sum += motion.changed_fraction
                motion_count += 1
            previous_id = frame.frame_id

            if time.perf_counter() >= deadline:
                break
    finally:
        capture.close()

    duration_s = 0.0
    observed_fps = 0.0
    if first_timestamp_ns is not None and last_timestamp_ns is not None:
        duration_s = max(0.0, (last_timestamp_ns - first_timestamp_ns) / 1_000_000_000)
        if duration_s > 0 and frame_count > 1:
            observed_fps = (frame_count - 1) / duration_s

    summary = {
        "type": "eyes_capture_summary",
        "captured_frames": frame_count,
        "capture_span_s": duration_s,
        "observed_fps": observed_fps,
        "mean_changed_fraction": (changed_sum / motion_count) if motion_count else 0.0,
        "saved_samples": sample_index,
        "buffer_seconds": buffer_seconds,
        **service.health(),
    }

    if output:
        (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="editgpt-eyes")
    sub = parser.add_subparsers(dest="command", required=True)
    capture = sub.add_parser("capture", help="capture live Windows frames")
    capture.add_argument("--seconds", type=float, default=5.0)
    capture.add_argument("--fps", type=int, default=60)
    capture.add_argument(
        "--buffer-seconds",
        type=float,
        default=0.5,
        help="exact in-memory rolling history; 0.5 s avoids multi-GB buffers",
    )
    capture.add_argument(
        "--save-dir",
        default="artifacts/eyes-live-proof",
        help="write one JPEG sample per second plus summary.json; empty disables",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "capture":
        if args.seconds <= 0:
            raise SystemExit("--seconds must be positive")
        if args.fps <= 0:
            raise SystemExit("--fps must be positive")
        if args.buffer_seconds <= 0:
            raise SystemExit("--buffer-seconds must be positive")
        return _capture(
            args.seconds,
            args.fps,
            args.buffer_seconds,
            args.save_dir or None,
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
