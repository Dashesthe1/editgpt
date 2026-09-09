import numpy as np

from editgpt.eyes import EyesService, FramePacket


def test_motion_measurement_and_health() -> None:
    service = EyesService(buffer_capacity=10)
    a = np.zeros((4, 4, 3), dtype=np.uint8)
    b = a.copy()
    b[:2, :, :] = 100

    service.ingest(FramePacket(1, 100, a, source="test"))
    service.ingest(FramePacket(2, 200, b, source="test"))

    motion = service.measure_motion(1, 2, pixel_threshold=12)
    assert motion.mean_abs_delta == 50.0
    assert motion.changed_fraction == 0.5
    assert service.health()["latest_frame_id"] == 2


def test_inspect_returns_only_retained_frames() -> None:
    service = EyesService(buffer_capacity=2)
    image = np.zeros((1, 1), dtype=np.uint8)
    for i in range(1, 4):
        service.ingest(FramePacket(i, i, image, source="test"))
    assert [f.frame_id for f in service.inspect_frames([1, 2, 3])] == [2, 3]
