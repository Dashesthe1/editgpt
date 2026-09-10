from __future__ import annotations

import json
from typing import Any

import numpy as np
import pytest

from editgpt.eyes.semantic import LocalQwenVLClient


class _Response:
    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(
            {"choices": [{"message": {"content": "sequence understood"}}]}
        ).encode("utf-8")


def test_observe_images_sends_labeled_sequence_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: float) -> _Response:
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr("editgpt.eyes.semantic.urllib.request.urlopen", fake_urlopen)
    client = LocalQwenVLClient(timeout_s=7.0)
    first = np.zeros((8, 8, 3), dtype=np.uint8)
    second = np.full((8, 8, 3), 255, dtype=np.uint8)
    result = client.observe_images(
        [first, second],
        prompt="Describe the visual change in chronological order.",
        labels=["index=2 time=0.2s", "index=7 time=0.7s"],
        source="source:test",
    )

    content = captured["body"]["messages"][0]["content"]
    assert [item["type"] for item in content] == [
        "text", "text", "image_url", "text", "image_url"
    ]
    assert content[1]["text"] == "Frame 1: index=2 time=0.2s"
    assert content[3]["text"] == "Frame 2: index=7 time=0.7s"
    assert content[2]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert result.text == "sequence understood"
    assert result.source == "source:test"
    assert captured["timeout"] == 7.0


def test_observe_images_rejects_unbounded_or_mislabeled_sequence() -> None:
    client = LocalQwenVLClient()
    image = np.zeros((2, 2, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="at most 12"):
        client.observe_images([image] * 13, prompt="test")
    with pytest.raises(ValueError, match="labels must match"):
        client.observe_images([image, image], prompt="test", labels=["only one"])
    with pytest.raises(ValueError, match="at least one image"):
        client.observe_images([], prompt="test")
