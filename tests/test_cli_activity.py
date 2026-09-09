import numpy as np

from editgpt.cli import _activity_probe


def test_activity_probe_detects_static_and_active_frames() -> None:
    black = np.zeros((64, 64, 3), dtype=np.uint8)
    white = np.full((64, 64, 3), 255, dtype=np.uint8)

    probe, first_fraction = _activity_probe(black, None, stride=8)
    assert first_fraction is None

    next_probe, static_fraction = _activity_probe(black, probe, stride=8)
    assert static_fraction == 0.0

    _, active_fraction = _activity_probe(white, next_probe, stride=8)
    assert active_fraction == 1.0
