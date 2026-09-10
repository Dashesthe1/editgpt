from __future__ import annotations

from pathlib import Path

import av
import numpy as np
import pytest

from editgpt.eyes.source import PyAVSourceReader, SourceCatalog, open_video_source


def _write_fixture(path: Path, *, count: int = 8, fps: int = 10) -> None:
    with av.open(str(path), mode="w") as container:
        stream = container.add_stream("mpeg4", rate=fps)
        stream.width = 96
        stream.height = 64
        stream.pix_fmt = "yuv420p"
        for index in range(count):
            image = np.full((64, 96, 3), index * 25, dtype=np.uint8)
            frame = av.VideoFrame.from_ndarray(image, format="bgr24")
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)


def test_pyav_source_reads_exact_decode_indices_and_pts(tmp_path: Path) -> None:
    path = tmp_path / "source.mp4"
    _write_fixture(path)
    reader = PyAVSourceReader(path)

    frames = reader.read_frames([0, 3, 7])
    assert [frame.frame_id for frame in frames] == [0, 3, 7]
    assert [frame.metadata["frame_index"] for frame in frames] == [0, 3, 7]
    assert [frame.metadata["source_time_s"] for frame in frames] == pytest.approx([0.0, 0.3, 0.7])
    assert all(frame.metadata["clock"] == "source_media" for frame in frames)
    assert all(frame.metadata["color_order"] == "BGR" for frame in frames)
    assert float(frames[1].image.mean()) > float(frames[0].image.mean())
    assert reader.index_at_seconds(0.35) == 4
    with pytest.raises(IndexError):
        reader.read_frame(99)


def test_open_video_source_falls_back_without_gpu(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "fallback.mp4"
    _write_fixture(path, count=4)

    def fail_gpu(*args: object, **kwargs: object) -> object:
        raise RuntimeError("gpu unavailable for test")

    monkeypatch.setattr("editgpt.eyes.source.PyNvVideoCodecSourceReader", fail_gpu)
    reader = open_video_source(path, prefer_gpu=True)
    assert reader.metadata.backend == "pyav"
    assert reader.metadata.exact_indexing is True
    assert reader.metadata.details["gpu_fallback_reason"] == "RuntimeError: gpu unavailable for test"


def test_source_catalog_reuses_open_source_and_closes(tmp_path: Path) -> None:
    path = tmp_path / "catalog.mp4"
    _write_fixture(path, count=3)
    catalog = SourceCatalog()
    first_id, first_meta = catalog.open(path, prefer_gpu=False)
    second_id, second_meta = catalog.open(path, prefer_gpu=False)
    assert first_id == second_id
    assert first_meta.path == second_meta.path
    assert catalog.health()["open_sources"] == 1
    assert catalog.get(first_id).read_frame(2).frame_id == 2
    assert catalog.close(first_id) is True
    assert catalog.close(first_id) is False

