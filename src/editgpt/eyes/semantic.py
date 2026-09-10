from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

import numpy as np


DEFAULT_MODEL = "Qwen/Qwen3-VL-8B-Instruct-GGUF:Q8_0"
DEFAULT_BASE_URL = "http://127.0.0.1:8080/v1"


@dataclass(frozen=True)
class SemanticObservation:
    model: str
    text: str
    latency_s: float
    source: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": "editgpt_semantic_observation",
            "model": self.model,
            "text": self.text,
            "latency_s": self.latency_s,
            "source": self.source,
        }


def encode_jpeg_data_url(
    image: np.ndarray,
    *,
    max_width: int = 1280,
    quality: int = 90,
) -> str:
    if max_width <= 0:
        raise ValueError("max_width must be positive")
    if not 40 <= quality <= 100:
        raise ValueError("quality must be between 40 and 100")

    try:
        import cv2  # type: ignore
    except ImportError as exc:
        raise RuntimeError("OpenCV is required for semantic image encoding") from exc

    view = image
    height, width = view.shape[:2]
    if width > max_width:
        scale = max_width / float(width)
        view = cv2.resize(
            view,
            (max_width, max(1, int(round(height * scale)))),
            interpolation=cv2.INTER_AREA,
        )

    ok, encoded = cv2.imencode(
        ".jpg",
        view,
        [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)],
    )
    if not ok:
        raise RuntimeError("failed to JPEG-encode semantic Eyes frame")

    payload = base64.b64encode(encoded.tobytes()).decode("ascii")
    return f"data:image/jpeg;base64,{payload}"


class LocalQwenVLClient:
    """OpenAI-compatible client for a local llama.cpp Qwen3-VL server.

    The client deliberately has no OpenAI/cloud dependency. Its only network
    activity is loopback HTTP to the local VLM server unless base_url is
    explicitly changed.
    """

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout_s: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s

    def health(self) -> dict[str, Any]:
        url = f"{self.base_url}/models"
        req = urllib.request.Request(url, method="GET")
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=min(self.timeout_s, 5.0)) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            return {
                "ok": False,
                "base_url": self.base_url,
                "model": self.model,
                "error": f"{type(exc).__name__}: {exc}",
            }
        return {
            "ok": True,
            "base_url": self.base_url,
            "model": self.model,
            "latency_s": time.perf_counter() - started,
            "server_models": body.get("data", []),
        }

    def observe_images(
        self,
        images: list[np.ndarray],
        *,
        prompt: str,
        labels: list[str] | None = None,
        source: str = "frame_sequence",
        max_tokens: int = 480,
        max_width: int = 960,
        jpeg_quality: int = 88,
    ) -> SemanticObservation:
        if not prompt.strip():
            raise ValueError("prompt must not be empty")
        if not images:
            raise ValueError("at least one image is required")
        if len(images) > 12:
            raise ValueError("at most 12 images may be sent in one semantic observation")
        if labels is not None and len(labels) != len(images):
            raise ValueError("labels must match the number of images")
        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive")

        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for offset, image in enumerate(images):
            if labels is not None:
                content.append(
                    {
                        "type": "text",
                        "text": f"Frame {offset + 1}: {labels[offset]}",
                    }
                )
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": encode_jpeg_data_url(
                            image,
                            max_width=max_width,
                            quality=jpeg_quality,
                        )
                    },
                }
            )

        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0.0,
            "max_tokens": max_tokens,
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"local Qwen server returned HTTP {exc.code}: {detail}"
            ) from exc
        except (OSError, urllib.error.URLError) as exc:
            raise RuntimeError(
                f"cannot reach local Qwen server at {self.base_url}; start llama.cpp first"
            ) from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError("local Qwen server returned invalid JSON") from exc

        try:
            text = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"unexpected local Qwen response shape: {payload!r}") from exc

        return SemanticObservation(
            model=self.model,
            text=str(text).strip(),
            latency_s=time.perf_counter() - started,
            source=source,
        )

    def observe(
        self,
        image: np.ndarray,
        *,
        prompt: str,
        source: str = "live_frame",
        max_tokens: int = 320,
        max_width: int = 1280,
        jpeg_quality: int = 90,
    ) -> SemanticObservation:
        return self.observe_images(
            [image],
            prompt=prompt,
            source=source,
            max_tokens=max_tokens,
            max_width=max_width,
            jpeg_quality=jpeg_quality,
        )
