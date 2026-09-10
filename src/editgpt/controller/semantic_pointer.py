from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import numpy as np

from editgpt.eyes.semantic import LocalQwenVLClient, SemanticObservation


@dataclass(frozen=True)
class SemanticPointerTarget:
    x: int
    y: int
    confidence: float
    target: str
    reason: str
    bbox_pixels: tuple[int, int, int, int] | None = None

    @classmethod
    def from_json_text(cls, text: str, *, width: int, height: int) -> "SemanticPointerTarget":
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`").strip()
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].lstrip()
        payload = json.loads(cleaned)
        if not isinstance(payload, dict):
            raise ValueError("semantic pointer response must be a JSON object")
        bbox_pixels: tuple[int, int, int, int] | None = None
        bbox = payload.get("bbox_2d")
        if isinstance(bbox, list) and len(bbox) == 4:
            values = [float(v) for v in bbox]
            if any(v < 0.0 or v > 1000.0 for v in values):
                raise ValueError("normalized semantic bbox must stay within 0..1000")
            x1 = int(round(values[0] / 1000.0 * (width - 1)))
            y1 = int(round(values[1] / 1000.0 * (height - 1)))
            x2 = int(round(values[2] / 1000.0 * (width - 1)))
            y2 = int(round(values[3] / 1000.0 * (height - 1)))
            if x2 <= x1 or y2 <= y1:
                raise ValueError("semantic bbox must have positive area")
            bbox_pixels = (x1, y1, x2, y2)
            x = int(round((x1 + x2) / 2.0))
            y = int(round((y1 + y2) / 2.0))
        else:
            x = int(payload["x"])
            y = int(payload["y"])

        if x < 0 or y < 0 or x >= width or y >= height:
            raise ValueError("semantic pointer is outside the model-visible frame")
        confidence = float(payload.get("confidence", 0.0))
        if confidence < 0.0 or confidence > 1.0:
            raise ValueError("semantic pointer confidence must be between 0 and 1")
        return cls(x=x, y=y, confidence=confidence, target=str(payload.get("target", "")),
                   reason=str(payload.get("reason", "")), bbox_pixels=bbox_pixels)


def choose_pointer_target(
    image: np.ndarray,
    *,
    instruction: str,
    client: LocalQwenVLClient,
    min_confidence: float = 0.55,
) -> tuple[SemanticPointerTarget, SemanticObservation]:
    height, width = image.shape[:2]
    prompt = f"""You are the GUI grounding controller for EditGPT inside Adobe After Effects.
Task: {instruction}
Locate only the visible requested target. Return only JSON with keys:
target, bbox_2d, confidence, reason.
bbox_2d must be [x1,y1,x2,y2] in normalized 0..1000 coordinates over the FULL image,
with origin at top-left. Make the box tightly bound the requested visible UI element.
Do not return raw pixel coordinates. Do not infer hidden controls.
If the target is not clearly visible, set confidence below 0.55.
"""
    observation = client.observe(
        image, prompt=prompt, source="live_eyes_pointer_target", max_tokens=180,
        max_width=width, jpeg_quality=92,
    )
    target = SemanticPointerTarget.from_json_text(observation.text, width=width, height=height)
    if target.confidence < min_confidence:
        raise ValueError(
            f"semantic pointer confidence {target.confidence:.2f} is below required {min_confidence:.2f}"
        )
    if target.bbox_pixels is None:
        return target, observation

    # Qwen grounding boxes can include a little vertical UI padding. Use a
    # conservative upper-interior click point rather than a second VLM crop pass, which
    # proved less stable on tiny AE menu labels. This remains inside the box.
    x1, y1, x2, y2 = target.bbox_pixels
    click_x = int(round((x1 + x2) / 2.0))
    click_y = min(y2 - 1, y1 + 2) if y2 <= height * 0.15 else int(round(y1 + (y2 - y1) * 0.40))
    result = SemanticPointerTarget(
        x=click_x,
        y=click_y,
        confidence=target.confidence,
        target=target.target,
        reason=target.reason,
        bbox_pixels=target.bbox_pixels,
    )
    return result, observation
