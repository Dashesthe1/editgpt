"""EditGPT Eyes public API."""

from .buffer import FrameBuffer
from .service import EyesService
from .source import (
    PyAVSourceReader,
    PyNvVideoCodecSourceReader,
    SourceCatalog,
    VideoSourceMetadata,
    open_video_source,
    source_backend_health,
)
from .temporal import TemporalAnalyzer, TemporalCandidate, TemporalEventResult, TemporalProfile
from .types import FramePacket, MotionObservation

__all__ = [
    "EyesService",
    "FrameBuffer",
    "FramePacket",
    "MotionObservation",
    "PyAVSourceReader",
    "PyNvVideoCodecSourceReader",
    "SourceCatalog",
    "TemporalAnalyzer",
    "TemporalCandidate",
    "TemporalEventResult",
    "TemporalProfile",
    "VideoSourceMetadata",
    "open_video_source",
    "source_backend_health",
]
