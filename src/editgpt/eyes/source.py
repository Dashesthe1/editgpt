from __future__ import annotations

import contextlib
import importlib
import io
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from .types import FramePacket

def _import_pynv() -> Any:
    try:
        sink = io.StringIO()
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            return importlib.import_module("PyNvVideoCodec")
    except Exception as exc:
        raise RuntimeError(
            f"PyNvVideoCodec is unavailable: {type(exc).__name__}: {exc}"
        ) from exc


@dataclass(slots=True, frozen=True)
class VideoSourceMetadata:
    path: str
    backend: str
    width: int
    height: int
    frame_count: int | None
    fps: float | None
    duration_s: float | None
    exact_indexing: bool
    hardware_accelerated: bool
    details: dict[str, Any] = field(default_factory=dict, compare=False)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class VideoSourceReader(Protocol):
    metadata: VideoSourceMetadata
    def read_frame(self, index: int) -> FramePacket: ...

    def read_frames(self, indices: list[int]) -> list[FramePacket]: ...

    def index_at_seconds(self, seconds: float) -> int: ...

    def close(self) -> None: ...


def _validate_indices(indices: list[int]) -> list[int]:
    if not indices:
        raise ValueError("at least one source frame index is required")
    parsed = [int(index) for index in indices]
    if any(index < 0 for index in parsed):
        raise ValueError("source frame indices must be non-negative")
    return parsed


def _packet(
    *,
    path: Path,
    backend: str,
    index: int,
    image_bgr: np.ndarray,
    timestamp_s: float,
    metadata: dict[str, Any] | None = None,
) -> FramePacket:
    details = {
        "frame_index": index,
        "source_time_s": timestamp_s,
        "clock": "source_media",
        "color_order": "BGR",
        "backend": backend,
    }
    if metadata:
        details.update(metadata)
    return FramePacket(
        frame_id=index,
        timestamp_ns=int(round(timestamp_s * 1_000_000_000)),
        image=np.array(image_bgr, copy=True),
        source=f"source:{path}",
        metadata=details,
    )


class PyAVSourceReader:
    """Exact decode-order source-frame access using PyAV/FFmpeg.

    This backend favors correctness over random-seek speed: a batch is decoded
    once in presentation order through the highest requested index. Source PTS
    is retained on every returned frame so VFR media is not forced onto a CFR
    clock. The NVIDIA backend is preferred when it is healthy.
    """

    def __init__(self, path: str | Path) -> None:
        try:
            import av  # type: ignore
        except ImportError as exc:
            raise RuntimeError("PyAV is required for CPU source decoding") from exc

        self._av = av
        self.path = Path(path).expanduser().resolve()
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        with av.open(str(self.path)) as container:
            if not container.streams.video:
                raise ValueError(f"source has no video stream: {self.path}")
            stream = container.streams.video[0]
            fps = float(stream.average_rate) if stream.average_rate else None
            duration_s = None
            if stream.duration is not None and stream.time_base is not None:
                duration_s = float(stream.duration * stream.time_base)
            elif container.duration is not None:
                duration_s = float(container.duration / av.time_base)
            self.metadata = VideoSourceMetadata(
                path=str(self.path),
                backend="pyav",
                width=int(stream.width),
                height=int(stream.height),
                frame_count=int(stream.frames) if stream.frames else None,
                fps=fps,
                duration_s=duration_s,
                exact_indexing=True,
                hardware_accelerated=False,
                details={
                    "codec": getattr(stream.codec_context, "name", None),
                    "time_base": str(stream.time_base) if stream.time_base else None,
                    "timing_basis": "decoded_frame_pts",
                },
            )

    def read_frame(self, index: int) -> FramePacket:
        return self.read_frames([index])[0]

    def read_frames(self, indices: list[int]) -> list[FramePacket]:
        requested = _validate_indices(indices)
        wanted = set(requested)
        highest = max(wanted)
        found: dict[int, FramePacket] = {}
        with self._av.open(str(self.path)) as container:
            stream = container.streams.video[0]
            for decoded_index, frame in enumerate(container.decode(stream)):
                if decoded_index in wanted:
                    if frame.time is not None:
                        timestamp_s = float(frame.time)
                    elif frame.pts is not None and frame.time_base is not None:
                        timestamp_s = float(frame.pts * frame.time_base)
                    elif self.metadata.fps:
                        timestamp_s = decoded_index / self.metadata.fps
                    else:
                        timestamp_s = 0.0
                    found[decoded_index] = _packet(
                        path=self.path,
                        backend="pyav",
                        index=decoded_index,
                        image_bgr=frame.to_ndarray(format="bgr24"),
                        timestamp_s=timestamp_s,
                        metadata={
                            "pts": frame.pts,
                            "time_base": str(frame.time_base) if frame.time_base else None,
                            "is_corrupt": bool(frame.is_corrupt),
                        },
                    )
                if decoded_index >= highest:
                    break

        missing = [index for index in requested if index not in found]
        if missing:
            raise IndexError(f"source frame index out of range: {missing[0]}")
        return [found[index] for index in requested]

    def index_at_seconds(self, seconds: float) -> int:
        if seconds < 0:
            raise ValueError("seconds must be non-negative")
        last_index = 0
        with self._av.open(str(self.path)) as container:
            stream = container.streams.video[0]
            for index, frame in enumerate(container.decode(stream)):
                last_index = index
                frame_time = frame.time
                if frame_time is None and frame.pts is not None and frame.time_base is not None:
                    frame_time = float(frame.pts * frame.time_base)
                if frame_time is None and self.metadata.fps:
                    frame_time = index / self.metadata.fps
                if frame_time is not None and float(frame_time) >= seconds:
                    return index
        return last_index

    def close(self) -> None:
        return None


class PyNvVideoCodecSourceReader:
    """NVIDIA NVDEC random-access source reader using SimpleDecoder."""

    def __init__(self, path: str | Path, *, gpu_id: int = 0) -> None:
        nvc = _import_pynv()

        self._nvc = nvc
        self.path = Path(path).expanduser().resolve()
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        self._decoder = nvc.SimpleDecoder(
            str(self.path),
            gpu_id=gpu_id,
            use_device_memory=False,
            output_color_type=nvc.OutputColorType.RGB,
            need_scanned_stream_metadata=True,
        )
        stream_meta = self._decoder.get_stream_metadata()
        fps = float(stream_meta.avg_frame_rate) if stream_meta.avg_frame_rate else None
        frame_count = len(self._decoder)
        self.metadata = VideoSourceMetadata(
            path=str(self.path),
            backend="pynvvideocodec",
            width=int(stream_meta.width),
            height=int(stream_meta.height),
            frame_count=int(frame_count),
            fps=fps,
            duration_s=float(stream_meta.duration) if stream_meta.duration else None,
            exact_indexing=True,
            hardware_accelerated=True,
            details={
                "codec": str(stream_meta.codec),
                "gpu_id": gpu_id,
                "timing_basis": "decoder_index_mapping",
            },
        )

    def _to_bgr(self, decoded: Any) -> np.ndarray:
        try:
            rgb = np.from_dlpack(decoded)
        except Exception:
            rgb = np.asarray(decoded)
        rgb = np.array(rgb, copy=True)
        if rgb.ndim != 3 or rgb.shape[-1] < 3:
            raise RuntimeError(f"unexpected NVDEC RGB frame shape: {rgb.shape}")
        return np.ascontiguousarray(rgb[..., :3][..., ::-1])

    def read_frame(self, index: int) -> FramePacket:
        return self.read_frames([index])[0]

    def read_frames(self, indices: list[int]) -> list[FramePacket]:
        requested = _validate_indices(indices)
        count = self.metadata.frame_count
        if count is not None and any(index >= count for index in requested):
            bad = next(index for index in requested if index >= count)
            raise IndexError(f"source frame index out of range: {bad}")
        decoded_frames = self._decoder.get_batch_frames_by_index(requested)
        if len(decoded_frames) != len(requested):
            raise RuntimeError("NVDEC returned an unexpected source-frame batch size")

        packets: list[FramePacket] = []
        for index, decoded in zip(requested, decoded_frames, strict=True):
            timestamp_s = index / self.metadata.fps if self.metadata.fps else 0.0
            packets.append(
                _packet(
                    path=self.path,
                    backend="pynvvideocodec",
                    index=index,
                    image_bgr=self._to_bgr(decoded),
                    timestamp_s=timestamp_s,
                    metadata={"decoder_pts": getattr(decoded, "timestamp", None)},
                )
            )
        return packets

    def index_at_seconds(self, seconds: float) -> int:
        if seconds < 0:
            raise ValueError("seconds must be non-negative")
        return int(self._decoder.get_index_from_time_in_seconds(float(seconds)))

    def close(self) -> None:
        self._decoder = None


def open_video_source(
    path: str | Path,
    *,
    prefer_gpu: bool = True,
    gpu_id: int = 0,
) -> VideoSourceReader:
    resolved = Path(path).expanduser().resolve()
    gpu_error: str | None = None
    if prefer_gpu:
        try:
            return PyNvVideoCodecSourceReader(resolved, gpu_id=gpu_id)
        except Exception as exc:
            gpu_error = f"{type(exc).__name__}: {exc}"

    reader = PyAVSourceReader(resolved)
    if gpu_error:
        reader.metadata.details["gpu_fallback_reason"] = gpu_error
    return reader


def source_backend_health() -> dict[str, Any]:
    result: dict[str, Any] = {"pynvvideocodec": False, "pyav": False}
    try:
        _import_pynv()
    except Exception as exc:
        result["pynvvideocodec_error"] = str(exc)
    else:
        result["pynvvideocodec"] = True
    try:
        import av  # type: ignore  # noqa: F401
    except Exception as exc:
        result["pyav_error"] = f"{type(exc).__name__}: {exc}"
    else:
        result["pyav"] = True
    result["ok"] = bool(result["pynvvideocodec"] or result["pyav"])
    return result



class SourceCatalog:
    """Session-local registry of explicitly opened read-only video sources."""

    def __init__(self) -> None:
        self._readers: dict[str, VideoSourceReader] = {}

    def open(
        self,
        path: str | Path,
        *,
        prefer_gpu: bool = True,
        gpu_id: int = 0,
    ) -> tuple[str, VideoSourceMetadata]:
        import hashlib

        resolved = Path(path).expanduser().resolve()
        source_id = "SRC_" + hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:12].upper()
        existing = self._readers.get(source_id)
        if existing is not None:
            return source_id, existing.metadata
        reader = open_video_source(resolved, prefer_gpu=prefer_gpu, gpu_id=gpu_id)
        self._readers[source_id] = reader
        return source_id, reader.metadata

    def get(self, source_id: str) -> VideoSourceReader:
        try:
            return self._readers[source_id]
        except KeyError as exc:
            raise KeyError(f"unknown source_id: {source_id}") from exc
    def close(self, source_id: str) -> bool:
        reader = self._readers.pop(source_id, None)
        if reader is None:
            return False
        reader.close()
        return True

    def close_all(self) -> None:
        for reader in list(self._readers.values()):
            reader.close()
        self._readers.clear()

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "open_sources": len(self._readers),
            "source_ids": sorted(self._readers),
            "backends": source_backend_health(),
        }
