from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict

from .eyes.backends.dxcam_capture import DXCamCapture
from .eyes.service import EyesService


def _capture(seconds: float, fps: int) -> int:
    service = EyesService(buffer_capacity=max(120, int(seconds * fps * 1.25)))
    capture = DXCamCapture()
    deadline = time.perf_counter() + seconds
    previous_id: int | None = None

    try:
        for frame in capture.frames(fps=fps):
            service.ingest(frame)
            if previous_id is not None:
                motion = service.measure_motion(previous_id, frame.frame_id)
                print(json.dumps({"type": "motion", **asdict(motion)}))
            previous_id = frame.frame_id
            if time.perf_counter() >= deadline:
                break
    finally:
        capture.close()

    print(json.dumps({"type": "health", **service.health()}))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="editgpt-eyes")
    sub = parser.add_subparsers(dest="command", required=True)
    capture = sub.add_parser("capture", help="capture live Windows frames")
    capture.add_argument("--seconds", type=float, default=5.0)
    capture.add_argument("--fps", type=int, default=60)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "capture":
        if args.seconds <= 0:
            raise SystemExit("--seconds must be positive")
        if args.fps <= 0:
            raise SystemExit("--fps must be positive")
        return _capture(args.seconds, args.fps)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
