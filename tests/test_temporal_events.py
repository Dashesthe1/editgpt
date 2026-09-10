from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from editgpt.eyes.source import VideoSourceMetadata
from editgpt.eyes.temporal import TemporalAnalyzer, TemporalProfile
from editgpt.eyes.types import FramePacket


@dataclass
class _Obs:
    text: str


class _Semantic:
    def __init__(self) -> None:
        self.calls = 0
        self.images = 0

    def observe_images(self, images, *, prompt, labels=None, **kwargs):
        self.calls += 1
        self.images += len(images)
        frames = []
        for label in labels or []:
            index = int(label.split("index=")[1].split()[0])
            match = index >= 5
            frames.append({"index": index, "match": match, "confidence": 0.95, "reason": "fixture"})
        import json
        return _Obs(json.dumps({"frames": frames, "uncertainty": None}))


class _Reader:
    def __init__(self, path: Path) -> None:
        self.metadata = VideoSourceMetadata(
            path=str(path), backend="fixture", width=8, height=8,
            frame_count=10, fps=10.0, duration_s=1.0,
            exact_indexing=True, hardware_accelerated=False,
        )

    def read_frames(self, indices):
        return [FramePacket(
            frame_id=i, timestamp_ns=i * 100_000_000,
            image=np.zeros((8, 8, 3), dtype=np.uint8), source="fixture",
            metadata={"source_time_s": i / 10.0},
        ) for i in indices]


def _profile(path: Path) -> TemporalProfile:
    values = np.zeros(10, dtype=np.float32)
    values[6] = 0.9
    return TemporalProfile(
        path=str(path), fps=10.0, frame_count=10, duration_s=1.0,
        backend="fixture", decode_s=0.0, analysis_s=0.0,
        transition_probabilities=values,
        mean_abs_delta=values.copy(), changed_fraction=values.copy(),
        flow_mean=values.copy(), acceleration=values.copy(),
        luma=np.linspace(0.1, 0.9, 10, dtype=np.float32),
        timestamps_s=np.arange(10, dtype=np.float64) / 10.0,
    )


def test_signal_event_finds_transition(tmp_path: Path) -> None:
    path = tmp_path / "fixture.mp4"
    path.write_bytes(b"fixture")
    reader = _Reader(path)
    analyzer = TemporalAnalyzer(prefer_transnet=False)
    analyzer._profiles[analyzer._cache_key(path)] = _profile(path)
    result = analyzer.find_event(reader, event_type="transition")
    assert result.found is True
    assert result.frame_index == 6
    assert result.backend == "fixture"


def test_semantic_appearance_refines_boundary(tmp_path: Path) -> None:
    path = tmp_path / "fixture.mp4"
    path.write_bytes(b"fixture")
    reader = _Reader(path)
    analyzer = TemporalAnalyzer(prefer_transnet=False, semantic_client=_Semantic())
    analyzer._profiles[analyzer._cache_key(path)] = _profile(path)
    result = analyzer.find_event(
        reader, event_type="appearance", description="the subject is visible", tolerance_frames=1
    )
    assert result.found is True
    assert result.frame_index == 5
    assert result.timestamp_s == 0.5
    assert result.bracket is not None


def test_semantic_disappearance_can_report_not_found(tmp_path: Path) -> None:
    path = tmp_path / "fixture.mp4"
    path.write_bytes(b"fixture")
    reader = _Reader(path)
    analyzer = TemporalAnalyzer(prefer_transnet=False, semantic_client=_Semantic())
    analyzer._profiles[analyzer._cache_key(path)] = _profile(path)
    result = analyzer.find_event(reader, event_type="disappearance", description="the subject is visible")
    assert result.found is False
    assert result.frame_index is None


def test_semantic_repeat_reuses_exact_frame_cache(tmp_path: Path) -> None:
    path = tmp_path / "fixture.mp4"
    path.write_bytes(b"fixture")
    reader = _Reader(path)
    semantic = _Semantic()
    analyzer = TemporalAnalyzer(prefer_transnet=False, semantic_client=semantic)
    analyzer._profiles[analyzer._cache_key(path)] = _profile(path)
    first = analyzer.find_event(reader, event_type="appearance", description="the subject is visible", tolerance_frames=1)
    calls, images = semantic.calls, semantic.images
    second = analyzer.find_event(reader, event_type="appearance", description="the subject is visible", tolerance_frames=1)
    assert second.frame_index == first.frame_index
    assert second.bracket == first.bracket
    assert semantic.calls == calls
    assert semantic.images == images


class _GuidedReader(_Reader):
    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.guided_calls: list[tuple[list[int], list[float]]] = []

    def read_frames_at_timestamps(self, indices, timestamps_s):
        self.guided_calls.append((list(indices), list(timestamps_s)))
        return self.read_frames(indices)


def test_semantic_search_uses_timestamp_guided_source_reads(tmp_path: Path) -> None:
    path = tmp_path / "guided-fixture.mp4"
    path.write_bytes(b"fixture")
    reader = _GuidedReader(path)
    analyzer = TemporalAnalyzer(prefer_transnet=False, semantic_client=_Semantic())
    analyzer._profiles[analyzer._cache_key(path)] = _profile(path)
    result = analyzer.find_event(reader, event_type="appearance", description="the subject is visible")
    assert result.found is True
    assert reader.guided_calls
    assert all(len(indices) == len(timestamps) for indices, timestamps in reader.guided_calls)
