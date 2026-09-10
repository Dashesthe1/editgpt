from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CoordinateTransform:
    encoded_width: int
    encoded_height: int
    capture_left: int
    capture_top: int
    scale_x: float
    scale_y: float

    @classmethod
    def from_status(cls, frame_metadata: dict[str, Any], hands_status: dict[str, Any]) -> "CoordinateTransform":
        geometry = frame_metadata.get("geometry") or {}
        encoded = geometry.get("encoded_pixels") or {}
        capture = geometry.get("capture_pixels") or {}
        source_meta = frame_metadata.get("metadata") or {}
        capture_region = source_meta.get("capture_region_pixels")
        output_region = source_meta.get("output_region_pixels")
        backend = hands_status.get("backend") or {}
        virtual = backend.get("virtual_screen") or {}
        required_numbers = [
            encoded.get("width"), encoded.get("height"), capture.get("width"), capture.get("height"),
            virtual.get("left"), virtual.get("top"), virtual.get("width"), virtual.get("height"),
        ]
        if not all(isinstance(value, (int, float)) for value in required_numbers):
            raise ValueError("Eyes/Hands geometry metadata is incomplete")
        if not (isinstance(capture_region, list) and len(capture_region) == 4):
            raise ValueError("Eyes capture region metadata is missing")
        if not (isinstance(output_region, list) and len(output_region) == 4):
            raise ValueError("Eyes output region metadata is missing")

        output_left, output_top, output_right, output_bottom = [int(v) for v in output_region]
        virtual_left = int(virtual["left"])
        virtual_top = int(virtual["top"])
        virtual_width = int(virtual["width"])
        virtual_height = int(virtual["height"])
        if (output_left, output_top) != (0, 0):
            raise ValueError("DXcam output origin is not safely anchored to the Windows virtual desktop")
        if (output_right - output_left, output_bottom - output_top) != (virtual_width, virtual_height):
            raise ValueError("multi-monitor/output geometry is ambiguous; refusing unsafe coordinate mapping")
        if (virtual_left, virtual_top) != (0, 0):
            raise ValueError("non-zero virtual desktop origin requires explicit monitor-origin mapping")
        capture_left, capture_top, capture_right, capture_bottom = [int(v) for v in capture_region]
        capture_width = int(capture["width"])
        capture_height = int(capture["height"])
        if (capture_right - capture_left, capture_bottom - capture_top) != (capture_width, capture_height):
            raise ValueError("capture region and frame dimensions disagree")

        encoded_width = int(encoded["width"])
        encoded_height = int(encoded["height"])
        if encoded_width <= 0 or encoded_height <= 0:
            raise ValueError("encoded frame dimensions must be positive")
        return cls(
            encoded_width=encoded_width,
            encoded_height=encoded_height,
            capture_left=capture_left,
            capture_top=capture_top,
            scale_x=capture_width / float(encoded_width),
            scale_y=capture_height / float(encoded_height),
        )

    def encoded_to_screen(self, x: int | float, y: int | float) -> tuple[int, int]:
        if x < 0 or y < 0 or x >= self.encoded_width or y >= self.encoded_height:
            raise ValueError("encoded point is outside the model-visible frame")
        screen_x = self.capture_left + int(round(float(x) * self.scale_x))
        screen_y = self.capture_top + int(round(float(y) * self.scale_y))
        return screen_x, screen_y
