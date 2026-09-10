from __future__ import annotations

from typing import Any, Sequence

import pytest

from editgpt.hands.service import HandsService


class FakeBackend:
    def __init__(self) -> None:
        self.process_name = "AfterFX.exe"
        self.calls: list[tuple[Any, ...]] = []

    def status(self) -> dict[str, Any]:
        return {"platform": "fake"}

    def foreground_window(self) -> dict[str, Any]:
        return {
            "hwnd": 1,
            "title": "Adobe After Effects",
            "process_id": 42,
            "process_name": self.process_name,
        }

    def focus_window(self, process_name: str, title_contains: str | None = None) -> dict[str, Any]:
        self.process_name = process_name
        self.calls.append(("focus", process_name, title_contains))
        return self.foreground_window()

    def move(self, x: int, y: int) -> None:
        self.calls.append(("move", x, y))

    def click(self, button: str = "left", count: int = 1) -> None:
        self.calls.append(("click", button, count))

    def scroll(self, delta_x: int = 0, delta_y: int = 0) -> None:
        self.calls.append(("scroll", delta_x, delta_y))

    def press_keys(self, keys: Sequence[str]) -> None:
        self.calls.append(("keys", tuple(keys)))

    def type_text(self, text: str) -> None:
        self.calls.append(("type", text))

    def drag(self, path: Sequence[tuple[int, int]], button: str = "left") -> None:
        self.calls.append(("drag", tuple(path), button))


def test_hands_starts_disarmed() -> None:
    service = HandsService(FakeBackend())
    assert service.status()["armed"] is False
    with pytest.raises(PermissionError, match="disarmed"):
        service.execute({"type": "click", "x": 10, "y": 20})


def test_hands_rejects_wrong_foreground_process() -> None:
    backend = FakeBackend()
    service = HandsService(backend)
    service.arm()
    backend.process_name = "notepad.exe"
    with pytest.raises(PermissionError, match="foreground process"):
        service.execute({"type": "move", "x": 10, "y": 20})


def test_hands_dispatches_computer_style_actions() -> None:
    backend = FakeBackend()
    service = HandsService(backend)
    service.arm()

    service.execute({"type": "click", "x": 100, "y": 200, "button": "left"})
    service.execute({"type": "scroll", "scroll_x": -120, "scroll_y": 240})
    service.execute({"type": "keypress", "keys": ["CTRL", "K"]})
    service.execute({"type": "type", "text": "hello"})
    service.execute({"type": "drag", "path": [{"x": 1, "y": 2}, {"x": 3, "y": 4}]})

    assert ("move", 100, 200) in backend.calls
    assert ("click", "left", 1) in backend.calls
    assert ("scroll", -120, 240) in backend.calls
    assert ("keys", ("CTRL", "K")) in backend.calls
    assert ("type", "hello") in backend.calls
    assert ("drag", ((1, 2), (3, 4)), "left") in backend.calls


def test_focus_is_limited_to_allowlist() -> None:
    backend = FakeBackend()
    service = HandsService(backend)
    service.arm()
    with pytest.raises(PermissionError, match="allowlist"):
        service.focus_target("notepad.exe")

    result = service.focus_target("AfterFX.exe")
    assert result["ok"] is True
    assert backend.calls[-1][0] == "focus"


def test_custom_allowlist_is_normalized() -> None:
    backend = FakeBackend()
    service = HandsService(backend)
    service.arm(["  AfterFX.EXE  "])
    assert service.status()["allowed_processes"] == ["afterfx.exe"]
