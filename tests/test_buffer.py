import numpy as np
import pytest

from editgpt.eyes import FrameBuffer, FramePacket


def packet(frame_id: int, timestamp_ns: int | None = None) -> FramePacket:
    return FramePacket(
        frame_id=frame_id,
        timestamp_ns=timestamp_ns if timestamp_ns is not None else frame_id * 10,
        image=np.zeros((2, 2, 3), dtype=np.uint8),
        source="test",
    )


def test_buffer_is_bounded_and_exact() -> None:
    buffer = FrameBuffer(capacity=3)
    buffer.extend(packet(i) for i in range(1, 5))
    assert [f.frame_id for f in buffer.latest(10)] == [2, 3, 4]
    assert buffer.get(1) is None
    assert buffer.get(3).frame_id == 3
    assert [f.frame_id for f in buffer.range(2, 3)] == [2, 3]


def test_buffer_rejects_non_monotonic_identity() -> None:
    buffer = FrameBuffer(capacity=3)
    buffer.append(packet(1, 100))
    with pytest.raises(ValueError):
        buffer.append(packet(1, 110))
    with pytest.raises(ValueError):
        buffer.append(packet(2, 90))
