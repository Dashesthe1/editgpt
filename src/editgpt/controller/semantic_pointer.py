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
        x = int(payload["x"])
        y = int(payload["y"])
        if x < 0 or y < 0 or x >= width or y >= height:
            raise ValueError("semantic pointer is outside the model-visible frame")
        confidence = float(payload.get("confidence", 0.0))
        if confidence < 0.0 or confidence > 1.0:
            raise ValueError("semantic pointer confidence must be between 0 and 1")
        return cls(
            x=x,
            y=y,
            confidence=confidence,
            target=str(payload.get("target", "")),
            reason=str(payload.get("reason", "")),
        )


def choose_pointer_target(
    image: np.ndarray,
    *,
    instruction: str,
    client: LocalQwenVLClient,
    min_confidence: float = 0.55,
) -> tuple[SemanticPointerTarget, SemanticObservation]:
    height, width = image.shape[:2]
    prompt = f"""You are the visual pointing controller for EditGPT inside Adobe After Effects.
The image coordinate space is exactly {width}x{height} pixels, origin at top-left.
Task: {instruction}
Return only JSON with keys: target, x, y, confidence, reason.
Choose the CENTER of the visible target. x/y must be integer pixels in this image.
Do not infer hidden controls. If the target is not clearly visible, set confidence below 0.55.
"""
    observation = client.observe(
        image,
        prompt=prompt,
        source="live_eyes_pointer_target",
        max_tokens=180,
        max_width=width,
        jpeg_quality=92,
    )
    target = SemanticPointerTarget.from_json_text(observation.text, width=width, height=height)
    if target.confidence < min_confidence:
        raise ValueError(
            f"semantic pointer confidence {target.confidence:.2f} is below required {min_confidence:.2f}"
        )
    return target, observation
