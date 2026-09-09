from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from .eyes.backends.dxcam_capture import DXCamCapture
from .eyes.service import EyesService


def _activity_probe(
    image: np.ndarray,
    previous: np.ndarray | None,
    *,
    stride: int = 16,
    pixel_threshold: float = 12.0,
) -> tuple[np.ndarray, float | None]:
    """Cheap activity measurement for the capture hot path.

    Full-resolution motion analysis is deliberately excluded from live ingestion.
    A sparse int16 probe is enough to tell whether the captured desktop is active
    without starving the capture consumer.
    """

    sampled = image[::stride, ::stride]
    if sampled.ndim == 3:
        sampled = sampled[..., :3]
    probe = np.asarray(sampled, dtype=np.int16).copy()
    if previous is None or previous.shape != probe.shape:
        return probe, None

    delta = np.abs(probe - previous)
    if delta.ndim == 3:
        per_pixel = delta.mean(axis=2)
    else:
        per_pixel = delta
    return probe, float((per_pixel >= pixel_threshold).mean())


def _capture(
    seconds: float,
    fps: int,
    buffer_seconds: float,
    save_dir: str | None,
    start_delay: float,
) -> int:
    capacity = max(2, int(fps * buffer_seconds))
    service = EyesService(buffer_capacity=capacity)
    capture = DXCamCapture()

    output = Path(save_dir) if save_dir else None
    if output:
        output.mkdir(parents=True, exist_ok=True)

    if start_delay > 0:
        print(
            f"Eyes capture starts in {start_delay:g} seconds. "
            "Switch to After Effects now and start the Composition preview."
        )
        time.sleep(start_delay)

    started = time.perf_counter()
    deadline = started + seconds
    first_timestamp_ns: int | None = None
    last_timestamp_ns: int | None = None
    frame_count = 0
    changed_sum = 0.0
    activity_count = 0
    previous_probe: np.ndarray | None = None
    next_sample_at = 0.0
    samples: list[tuple[int, np.ndarray]] = []

    try:
        for frame in capture.frames(fps=fps):
            # Keep the ingestion path intentionally cheap. DXcam already gives us
            # an owned frame copy; heavy CV/VLM work must happen outside this loop.
            service.ingest(frame)
            frame_count += 1
            if first_timestamp_ns is None:
                first_timestamp_ns = frame.timestamp_ns
            last_timestamp_ns = frame.timestamp_ns

            previous_probe, changed_fraction = _activity_probe(
                frame.image, previous_probe
            )
            if changed_fraction is not None:
                changed_sum += changed_fraction
                activity_count += 1

            elapsed = time.perf_counter() - started
            if output and elapsed >= next_sample_at:
                # FramePacket owns its ndarray, so retaining this reference is safe
                # after the rolling Eyes buffer evicts the packet.
                samples.append((len(samples), frame.image))
                next_sample_at += 1.0

            if time.perf_counter() >= deadline:
                break
    finally:
        capture.close()

    wall_capture_s = max(0.0, time.perf_counter() - started)
    capture_span_s = 0.0
    observed_fps = 0.0
    if first_timestamp_ns is not None and last_timestamp_ns is not None:
        capture_span_s = max(
            0.0, (last_timestamp_ns - first_timestamp_ns) / 1_000_000_000
        )
        if capture_span_s > 0 and frame_count > 1:
            observed_fps = (frame_count - 1) / capture_span_s

    mean_changed_fraction = (
        changed_sum / activity_count if activity_count else 0.0
    )
    fps_ratio = observed_fps / fps if fps > 0 else 0.0
    if mean_changed_fraction < 1e-5:
        screen_activity = "near_static"
    elif mean_changed_fraction < 1e-3:
        screen_activity = "low"
    else:
        screen_activity = "active"

    if frame_count < 2:
        diagnostic = "insufficient_frames"
    elif fps_ratio < 0.5 and screen_activity == "near_static":
        diagnostic = "likely_static_or_obscured_target"
    elif fps_ratio < 0.5:
        diagnostic = "below_target_rate_needs_investigation"
    else:
        diagnostic = "capture_rate_healthy"

    if output:
        try:
            import cv2  # type: ignore
        except ImportError as exc:
            raise RuntimeError("Saving proof frames requires OpenCV.") from exc
        for sample_index, image in samples:
            cv2.imwrite(str(output / f"sample_{sample_index:03d}.jpg"), image)

    summary = {
        "type": "eyes_capture_summary",
        "target_fps": fps,
        "captured_frames": frame_count,
        "capture_span_s": capture_span_s,
        "wall_capture_s": wall_capture_s,
        "observed_fps": observed_fps,
        "fps_ratio": fps_ratio,
        "mean_changed_fraction": mean_changed_fraction,
        "screen_activity": screen_activity,
        "diagnostic": diagnostic,
        "saved_samples": len(samples),
        "buffer_seconds": buffer_seconds,
        **service.health(),
    }

    if output:
        (output / "summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
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
        "--start-delay",
        type=float,
        default=5.0,
        help="seconds to switch from PowerShell to AE and start preview",
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
        if args.start_delay < 0:
            raise SystemExit("--start-delay must not be negative")
        return _capture(
            args.seconds,
            args.fps,
            args.buffer_seconds,
            args.save_dir or None,
            args.start_delay,
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
