import numpy as np

from editgpt.eyes import EyesService, FramePacket


def test_retained_frame_is_independent_when_caller_owns_copy() -> None:
    """Documents the exact-history contract expected from capture backends."""
    original = np.zeros((2, 2, 3), dtype=np.uint8)
    retained = np.array(original, copy=True)
    service = EyesService(buffer_capacity=2)
    service.ingest(FramePacket(1, 1, retained, source="capture"))

    original[:] = 255
    assert int(service.buffer.get(1).image.max()) == 0
