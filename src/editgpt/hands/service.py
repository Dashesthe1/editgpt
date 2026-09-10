from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol, Sequence


class InputBackend(Protocol):
    """Platform input backend used by HandsService."""

    def status(self) -> dict[str, Any]: ...

    def foreground_window(self) -> dict[str, Any]: ...

    def focus_window(self, process_name: str, title_contains: str | None = None) -> dict[str, Any]: ...

    def move(self, x: int, y: int) -> None: ...

    def click(self, button: str = "left", count: int = 1) -> None: ...

    def scroll(self, delta_x: int = 0, delta_y: int = 0) -> None: ...

    def press_keys(self, keys: Sequence[str]) -> None: ...

    def type_text(self, text: str) -> None: ...

    def drag(self, path: Sequence[tuple[int, int]], button: str = "left") -> None: ...


def _normalize_process_name(value: str) -> str:
    cleaned = value.strip().lower()
    if not cleaned:
        raise ValueError("process name cannot be empty")
    return cleaned


def _required_int(action: dict[str, Any], name: str) -> int:
    value = action.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    return int(round(value))


@dataclass
class HandsState:
    armed: bool = False
    allowed_processes: tuple[str, ...] = ("afterfx.exe",)


class HandsService:
    """Guarded mouse/keyboard control for professional desktop editing.

    Hands is deliberately separate from Eyes. It is write-capable, starts
    disarmed, and checks the foreground process before every action.
    """

    def __init__(
        self,
        backend: InputBackend,
        *,
        default_allowed_processes: Sequence[str] = ("AfterFX.exe",),
    ) -> None:
        allowed = tuple(_normalize_process_name(name) for name in default_allowed_processes)
        if not allowed:
            raise ValueError("at least one allowed process is required")
        self.backend = backend
        self.state = HandsState(armed=False, allowed_processes=allowed)

    def arm(self) -> dict[str, Any]:
        """Arm the immutable process allowlist configured when the service was created."""
        self.state.armed = True
        return self.status()

    def disarm(self) -> dict[str, Any]:
        self.state.armed = False
        return self.status()

    def status(self) -> dict[str, Any]:
        foreground = self.backend.foreground_window()
        foreground_process = str(foreground.get("process_name") or "").lower()
        return {
            "type": "editgpt_hands_status",
            "armed": self.state.armed,
            "allowed_processes": list(self.state.allowed_processes),
            "foreground": foreground,
            "action_allowed": self.state.armed and foreground_process in self.state.allowed_processes,
            "backend": self.backend.status(),
            "supported_actions": [
                "click",
                "double_click",
                "move",
                "scroll",
                "keypress",
                "type",
                "drag",
                "wait",
            ],
        }

    def focus_target(self, process_name: str = "AfterFX.exe", title_contains: str | None = None) -> dict[str, Any]:
        self._require_armed()
        normalized = _normalize_process_name(process_name)
        if normalized not in self.state.allowed_processes:
            raise PermissionError(f"process is not in the Hands allowlist: {process_name}")
        result = self.backend.focus_window(process_name, title_contains=title_contains)
        foreground = self.backend.foreground_window()
        if str(foreground.get("process_name") or "").lower() != normalized:
            raise RuntimeError("requested target did not become the foreground window")
        return {"ok": True, "focus": result, "foreground": foreground}

    def execute(self, action: dict[str, Any]) -> dict[str, Any]:
        """Execute one OpenAI-computer-style action against the guarded desktop."""
        if not isinstance(action, dict):
            raise TypeError("action must be an object")
        action_type = str(action.get("type") or "").strip().lower()
        if not action_type:
            raise ValueError("action.type is required")

        if action_type == "wait":
            self._require_armed_and_foreground()
            wait_ms = _required_int(action, "ms") if "ms" in action else 500
            if wait_ms < 0 or wait_ms > 10_000:
                raise ValueError("wait ms must be between 0 and 10000")
            time.sleep(wait_ms / 1000.0)
            return self._result(action_type)

        self._require_armed_and_foreground()

        if action_type in {"click", "double_click"}:
            x = _required_int(action, "x")
            y = _required_int(action, "y")
            button = str(action.get("button") or "left").lower()
            self.backend.move(x, y)
            self.backend.click(button=button, count=2 if action_type == "double_click" else 1)
        elif action_type == "move":
            self.backend.move(_required_int(action, "x"), _required_int(action, "y"))
        elif action_type == "scroll":
            if "x" in action and "y" in action:
                self.backend.move(_required_int(action, "x"), _required_int(action, "y"))
            self.backend.scroll(
                delta_x=_required_int(action, "scroll_x") if "scroll_x" in action else 0,
                delta_y=_required_int(action, "scroll_y") if "scroll_y" in action else 0,
            )
        elif action_type in {"keypress", "key_press"}:
            keys = action.get("keys")
            if not isinstance(keys, list) or not keys or not all(isinstance(key, str) for key in keys):
                raise ValueError("keypress requires a non-empty string list in keys")
            self.backend.press_keys(keys)
        elif action_type == "type":
            text = action.get("text")
            if not isinstance(text, str):
                raise ValueError("type requires string text")
            self.backend.type_text(text)
        elif action_type == "drag":
            raw_path = action.get("path")
            if not isinstance(raw_path, list) or len(raw_path) < 2:
                raise ValueError("drag requires at least two path points")
            path: list[tuple[int, int]] = []
            for point in raw_path:
                if not isinstance(point, dict):
                    raise ValueError("drag path points must be objects")
                path.append((_required_int(point, "x"), _required_int(point, "y")))
            self.backend.drag(path, button=str(action.get("button") or "left").lower())
        else:
            raise ValueError(f"unsupported Hands action type: {action_type}")

        return self._result(action_type)

    def _require_armed(self) -> None:
        if not self.state.armed:
            raise PermissionError("EditGPT Hands is disarmed")

    def _require_armed_and_foreground(self) -> dict[str, Any]:
        self._require_armed()
        foreground = self.backend.foreground_window()
        process_name = str(foreground.get("process_name") or "").lower()
        if process_name not in self.state.allowed_processes:
            allowed = ", ".join(self.state.allowed_processes)
            raise PermissionError(
                f"foreground process {process_name or '<unknown>'!r} is not allowed; expected one of: {allowed}"
            )
        return foreground

    def _result(self, action_type: str) -> dict[str, Any]:
        return {
            "ok": True,
            "action_type": action_type,
            "foreground": self.backend.foreground_window(),
        }
