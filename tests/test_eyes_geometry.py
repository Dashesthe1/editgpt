from __future__ import annotations

import numpy as np

from editgpt.eyes.types import FramePacket
from editgpt.mcp_server import _encoded_dimensions, _frame_metadata


def test_encoded_dimensions_preserve_aspect_ratio() -> None:
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    assert _encoded_dimensions(image, 1280) == (1280, 720)
    assert _encoded_dimensions(image, 2560) == (1920, 1080)


def test_frame_metadata_exposes_coordinate_transform() -> None:
    frame = FramePacket(
        frame_id=7,
        timestamp_ns=123,
        image=np.zeros((1080, 1920, 3), dtype=np.uint8),
        source="dxcam",
        metadata={"capture_region_pixels": [0, 0, 1920, 1080]},
    )
    metadata = _frame_metadata(frame, max_width=1280)
    assert metadata["geometry"]["capture_pixels"] == {"width": 1920, "height": 1080}
    assert metadata["geometry"]["encoded_pixels"] == {"width": 1280, "height": 720}
    assert metadata["geometry"]["encoded_to_capture_scale"] == {"x": 1.5, "y": 1.5}
