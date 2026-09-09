from __future__ import annotations

import argparse
import json
from typing import Any

import numpy as np

from .eyes.runtime import LiveEyesRuntime

_RUNTIME = LiveEyesRuntime(buffer_capacity=30)


def _require_cv2():
    try:
        import cv2  # type: ignore
    except ImportError as exc:
        raise RuntimeError("OpenCV is required for MCP image encoding; install editgpt[capture,mcp].") from exc
    return cv2


def _encode_jpeg(image: np.ndarray, *, max_width: int = 1280, quality: int = 88) -> bytes:
    if max_width <= 0:
        raise ValueError("max_width must be positive")
    if not 40 <= quality <= 100:
        raise ValueError("quality must be between 40 and 100")

    cv2 = _require_cv2()
    view = image
    height, width = view.shape[:2]
    if width > max_width:
        scale = max_width / float(width)
        view = cv2.resize(
            view,
            (max_width, max(1, int(round(height * scale)))),
            interpolation=cv2.INTER_AREA,
        )
    ok, encoded = cv2.imencode(
        ".jpg",
        view,
        [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)],
    )
    if not ok:
        raise RuntimeError("failed to encode live Eyes frame")
    return encoded.tobytes()


def _frame_metadata(frame: Any) -> dict[str, Any]:
    return {
        "frame_id": frame.frame_id,
        "timestamp_ns": frame.timestamp_ns,
        "source": frame.source,
        "shape": list(frame.image.shape),
        "metadata": dict(frame.metadata),
    }


def build_server():
    try:
        from mcp.server.mcpserver import MCPServer
        from mcp.server.mcpserver.utilities.types import Image
    except ImportError as exc:
        raise RuntimeError("MCP SDK v2 is required; install editgpt[mcp].") from exc

    mcp = MCPServer("EditGPT Eyes")

    @mcp.tool()
    def eyes_start_live(
        fps: int = 60,
        monitor_index: int = 0,
        region: list[int] | None = None,
        buffer_seconds: float = 0.5,
    ) -> dict[str, Any]:
        """Start persistent live Windows capture for EditGPT Eyes.

        region is optional [left, top, right, bottom] screen coordinates.
        """
        parsed_region: tuple[int, int, int, int] | None = None
        if region is not None:
            if len(region) != 4:
                raise ValueError("region must contain exactly [left, top, right, bottom]")
            parsed_region = tuple(int(v) for v in region)  # type: ignore[assignment]
            left, top, right, bottom = parsed_region
            if right <= left or bottom <= top:
                raise ValueError("region must have positive width and height")
        return _RUNTIME.start(
            fps=fps,
            monitor_index=monitor_index,
            region=parsed_region,
            buffer_seconds=buffer_seconds,
        )

    @mcp.tool()
    def eyes_status() -> dict[str, Any]:
        """Return live Eyes capture health, timing, rate, and buffer state."""
        return _RUNTIME.status()

    @mcp.tool()
    def eyes_stop_live() -> dict[str, Any]:
        """Stop the persistent live Eyes capture session."""
        return _RUNTIME.stop()

    @mcp.tool(structured_output=False)
    def eyes_latest_frame(max_width: int = 1280, jpeg_quality: int = 88) -> list[str | Image]:
        """Return the newest retained screen frame as model-visible JPEG evidence."""
        frame = _RUNTIME.latest_frame()
        metadata = json.dumps(_frame_metadata(frame), separators=(",", ":"))
        return [
            metadata,
            Image(data=_encode_jpeg(frame.image, max_width=max_width, quality=jpeg_quality), format="jpeg"),
        ]

    @mcp.tool(structured_output=False)
    def eyes_recent_frames(
        count: int = 4,
        stride: int = 1,
        max_width: int = 960,
        jpeg_quality: int = 85,
    ) -> list[str | Image]:
        """Return a small chronological sequence of recent frames for temporal reasoning."""
        if count < 1 or count > 8:
            raise ValueError("count must be between 1 and 8")
        frames = _RUNTIME.recent_frames(count=count, stride=stride)
        if not frames:
            raise RuntimeError("no live frames are available")
        content: list[str | Image] = []
        for frame in frames:
            content.append(json.dumps(_frame_metadata(frame), separators=(",", ":")))
            content.append(
                Image(
                    data=_encode_jpeg(frame.image, max_width=max_width, quality=jpeg_quality),
                    format="jpeg",
                )
            )
        return content

    @mcp.tool(structured_output=False)
    def eyes_frame(
        frame_id: int,
        max_width: int = 1280,
        jpeg_quality: int = 90,
    ) -> list[str | Image]:
        """Return one exact retained frame by EditGPT frame ID."""
        frame = _RUNTIME.service.buffer.get(frame_id)
        if frame is None:
            raise KeyError("requested frame is not present in the rolling buffer")
        return [
            json.dumps(_frame_metadata(frame), separators=(",", ":")),
            Image(data=_encode_jpeg(frame.image, max_width=max_width, quality=jpeg_quality), format="jpeg"),
        ]

    @mcp.tool()
    def eyes_motion_between(
        earlier_frame_id: int,
        later_frame_id: int,
        pixel_threshold: float = 12.0,
    ) -> dict[str, Any]:
        """Measure pixel change between two exact retained frames."""
        return _RUNTIME.service.motion_as_dict(
            earlier_frame_id,
            later_frame_id,
            pixel_threshold=pixel_threshold,
        )

    return mcp


mcp = build_server()


def main() -> int:
    parser = argparse.ArgumentParser(prog="editgpt-eyes-mcp")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="streamable-http",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--allow-nonlocal-bind",
        action="store_true",
        help="explicitly allow binding the unauthenticated development server beyond loopback",
    )
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run("stdio")
        return 0

    loopback_hosts = {"127.0.0.1", "localhost", "::1"}
    if args.host not in loopback_hosts and not args.allow_nonlocal_bind:
        raise SystemExit(
            "Refusing a non-loopback bind for the unauthenticated development MCP. "
            "Use --allow-nonlocal-bind only for an explicitly protected test network."
        )

    mcp.run(
        "streamable-http",
        host=args.host,
        port=args.port,
        json_response=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
