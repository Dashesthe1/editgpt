from __future__ import annotations

import argparse
import json
import time

import dxcam


def run_phase(*, fps: int, seconds: float, video_mode: bool, monitor_index: int) -> dict[str, object]:
    camera = dxcam.create(output_idx=monitor_index, output_color="BGR")
    seen = 0
    unique_timestamps = 0
    previous_timestamp: float | None = None
    first_timestamp: float | None = None
    last_timestamp: float | None = None
    started = time.perf_counter()

    try:
        camera.start(target_fps=fps, video_mode=video_mode)
        deadline = started + seconds
        while time.perf_counter() < deadline:
            frame, timestamp = camera.get_latest_frame(with_timestamp=True)
            if frame is None:
                continue
            seen += 1
            if timestamp is not None:
                ts = float(timestamp)
                if first_timestamp is None:
                    first_timestamp = ts
                last_timestamp = ts
                if previous_timestamp is None or ts != previous_timestamp:
                    unique_timestamps += 1
                previous_timestamp = ts
    finally:
        camera.stop()
        camera.release()

    wall_s = max(1e-9, time.perf_counter() - started)
    present_span_s = 0.0
    unique_present_fps = 0.0
    if first_timestamp is not None and last_timestamp is not None and last_timestamp >= first_timestamp:
        present_span_s = last_timestamp - first_timestamp
        if present_span_s > 0 and unique_timestamps > 1:
            unique_present_fps = (unique_timestamps - 1) / present_span_s

    return {
        "video_mode": video_mode,
        "target_fps": fps,
        "consumer_frames": seen,
        "wall_s": wall_s,
        "consumer_fps": seen / wall_s,
        "unique_present_timestamps": unique_timestamps,
        "present_span_s": present_span_s,
        "unique_present_fps": unique_present_fps,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare truthful DXcam capture with paced duplicate-fill mode.")
    parser.add_argument("--fps", type=int, default=60)
    parser.add_argument("--seconds", type=float, default=3.0)
    parser.add_argument("--delay", type=float, default=5.0)
    parser.add_argument("--monitor-index", type=int, default=0)
    args = parser.parse_args()

    if args.fps <= 0 or args.seconds <= 0 or args.delay < 0:
        raise SystemExit("fps/seconds must be positive and delay must be non-negative")

    print(f"Capture diagnostic starts in {args.delay:g} seconds. Switch to After Effects and keep the preview playing.")
    time.sleep(args.delay)

    truthful = run_phase(
        fps=args.fps,
        seconds=args.seconds,
        video_mode=False,
        monitor_index=args.monitor_index,
    )
    paced = run_phase(
        fps=args.fps,
        seconds=args.seconds,
        video_mode=True,
        monitor_index=args.monitor_index,
    )

    paced_fps = float(paced["consumer_fps"])
    truthful_present = float(truthful["unique_present_fps"])
    paced_unique = float(paced["unique_present_fps"])

    if paced_fps >= args.fps * 0.9 and max(truthful_present, paced_unique) < args.fps * 0.9:
        interpretation = "runtime_can_sustain_target_but_windows_presented_fewer_unique_frames"
    elif paced_fps < args.fps * 0.9:
        interpretation = "capture_pipeline_throughput_below_target"
    else:
        interpretation = "capture_pipeline_and_unique_present_rate_healthy"

    result = {
        "type": "editgpt_dxcam_mode_probe",
        "truthful": truthful,
        "paced": paced,
        "interpretation": interpretation,
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
