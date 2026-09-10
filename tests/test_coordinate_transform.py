from __future__ import annotations

import pytest

from editgpt.controller.coordinates import CoordinateTransform


def _frame_meta() -> dict:
    return {
        "geometry": {
            "capture_pixels": {"width": 1920, "height": 1080},
            "encoded_pixels": {"width": 1280, "height": 720},
        },
        "metadata": {
            "output_region_pixels": [0, 0, 1920, 1080],
            "capture_region_pixels": [0, 0, 1920, 1080],
        },
    }


def _hands_status() -> dict:
    return {"backend": {"virtual_screen": {"left": 0, "top": 0, "width": 1920, "height": 1080}}}


def test_maps_model_visible_coordinates_to_physical_screen() -> None:
    transform = CoordinateTransform.from_status(_frame_meta(), _hands_status())
    assert transform.encoded_to_screen(640, 360) == (960, 540)


def test_rejects_ambiguous_multi_monitor_geometry() -> None:
    hands = _hands_status()
    hands["backend"]["virtual_screen"]["width"] = 3840
    with pytest.raises(ValueError, match="ambiguous"):
        CoordinateTransform.from_status(_frame_meta(), hands)


def test_rejects_points_outside_encoded_frame() -> None:
    transform = CoordinateTransform.from_status(_frame_meta(), _hands_status())
    with pytest.raises(ValueError, match="outside"):
        transform.encoded_to_screen(1280, 719)
