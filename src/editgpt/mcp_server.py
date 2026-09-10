from __future__ import annotations

import argparse
import json
from typing import Any

import numpy as np

from .eyes.runtime import LiveEyesRuntime
from .eyes.source import SourceCatalog
from .eyes.temporal import TemporalAnalyzer

_RUNTIME = LiveEyesRuntime(buffer_capacity=30)
_SOURCES = SourceCatalog()
_TEMPORAL = TemporalAnalyzer()


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


def _encoded_dimensions(image: np.ndarray, max_width: int) -> tuple[int, int]:
    height, width = image.shape[:2]
    if width <= max_width:
        return width, height
    scale = max_width / float(width)
    return max_width, max(1, int(round(height * scale)))


def _frame_metadata(frame: Any, *, max_width: int) -> dict[str, Any]:
    height, width = frame.image.shape[:2]
    encoded_width, encoded_height = _encoded_dimensions(frame.image, max_width)
    return {
        "frame_id": frame.frame_id,
        "timestamp_ns": frame.timestamp_ns,
        "source": frame.source,
        "shape": list(frame.image.shape),
        "metadata": dict(frame.metadata),
        "geometry": {
            "capture_pixels": {"width": width, "height": height},
            "encoded_pixels": {"width": encoded_width, "height": encoded_height},
            "encoded_to_capture_scale": {
                "x": width / float(encoded_width),
                "y": height / float(encoded_height),
            },
        },
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
    def eyes_latest_frame(max_width: int = 1280, jpeg_quality: int = 88) -> list[Any]:
        """Return the newest retained screen frame as model-visible JPEG evidence."""
        frame = _RUNTIME.latest_frame()
        metadata = json.dumps(_frame_metadata(frame, max_width=max_width), separators=(",", ":"))
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
    ) -> list[Any]:
        """Return a small chronological sequence of recent frames for temporal reasoning."""
        if count < 1 or count > 8:
            raise ValueError("count must be between 1 and 8")
        frames = _RUNTIME.recent_frames(count=count, stride=stride)
        if not frames:
            raise RuntimeError("no live frames are available")
        content: list[Any] = []
        for frame in frames:
            content.append(json.dumps(_frame_metadata(frame, max_width=max_width), separators=(",", ":")))
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
    ) -> list[Any]:
        """Return one exact retained frame by EditGPT frame ID."""
        frame = _RUNTIME.service.buffer.get(frame_id)
        if frame is None:
            raise KeyError("requested frame is not present in the rolling buffer")
        return [
            json.dumps(_frame_metadata(frame, max_width=max_width), separators=(",", ":")),
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


    @mcp.tool()
    def eyes_source_health() -> dict[str, Any]:
        """Return read-only source-video decoder health and open-source state."""
        return _SOURCES.health()

    @mcp.tool()
    def eyes_source_open(
        path: str,
        prefer_gpu: bool = True,
        gpu_id: int = 0,
    ) -> dict[str, Any]:
        """Open a local video source for exact read-only frame evidence."""
        source_id, metadata = _SOURCES.open(path, prefer_gpu=prefer_gpu, gpu_id=gpu_id)
        return {"source_id": source_id, "metadata": metadata.as_dict()}


    @mcp.tool()
    def eyes_source_info(source_id: str) -> dict[str, Any]:
        """Return metadata for an already opened source video."""
        return {"source_id": source_id, "metadata": _SOURCES.get(source_id).metadata.as_dict()}

    @mcp.tool(structured_output=False)
    def eyes_source_frame(
        source_id: str,
        index: int,
        max_width: int = 1280,
        jpeg_quality: int = 90,
    ) -> list[Any]:
        """Return one exact source-video frame by decode-order index."""
        frame = _SOURCES.get(source_id).read_frame(index)
        metadata = _frame_metadata(frame, max_width=max_width)
        metadata["source_id"] = source_id
        return [
            json.dumps(metadata, separators=(",", ":")),
            Image(data=_encode_jpeg(frame.image, max_width=max_width, quality=jpeg_quality), format="jpeg"),
        ]


    @mcp.tool(structured_output=False)
    def eyes_source_frames(
        source_id: str,
        indices: list[int],
        max_width: int = 960,
        jpeg_quality: int = 86,
    ) -> list[Any]:
        """Return up to 12 exact source frames in caller-specified order."""
        if not indices or len(indices) > 12:
            raise ValueError("indices must contain between 1 and 12 frame indices")
        frames = _SOURCES.get(source_id).read_frames(indices)
        content: list[Any] = []
        for frame in frames:
            metadata = _frame_metadata(frame, max_width=max_width)
            metadata["source_id"] = source_id
            content.append(json.dumps(metadata, separators=(",", ":")))
            content.append(
                Image(
                    data=_encode_jpeg(frame.image, max_width=max_width, quality=jpeg_quality),
                    format="jpeg",
                )
            )
        return content


    @mcp.tool()
    def eyes_source_index_at_time(source_id: str, seconds: float) -> dict[str, Any]:
        """Map source-media seconds to the first presented decode-order frame at/after that time."""
        reader = _SOURCES.get(source_id)
        index = reader.index_at_seconds(seconds)
        frame = reader.read_frame(index)
        return {
            "source_id": source_id,
            "requested_seconds": float(seconds),
            "frame_index": index,
            "source_time_s": frame.metadata.get("source_time_s"),
        }

    @mcp.tool()
    def eyes_source_temporal_profile(source_id: str, force: bool = False) -> dict[str, Any]:
        """Analyze and cache temporal structure, motion extrema, and transition candidates."""
        reader = _SOURCES.get(source_id)
        return _TEMPORAL.profile(reader, force=force).summary()

    @mcp.tool()
    def eyes_source_find_event(
        source_id: str,
        event_type: str,
        description: str | None = None,
        start_s: float = 0.0,
        end_s: float | None = None,
        tolerance_frames: int = 2,
    ) -> dict[str, Any]:
        """Locate a temporal event using machine signals and semantic verification when needed."""
        reader = _SOURCES.get(source_id)
        return _TEMPORAL.find_event(
            reader, event_type=event_type, description=description,
            start_s=start_s, end_s=end_s, tolerance_frames=tolerance_frames,
        ).as_dict()

    @mcp.tool()
    def eyes_source_close(source_id: str) -> dict[str, Any]:
        """Close one opened source-video reader without modifying the media."""
        return {"source_id": source_id, "closed": _SOURCES.close(source_id)}

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
