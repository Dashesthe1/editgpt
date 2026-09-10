from __future__ import annotations

import ctypes
import os
import time
from pathlib import Path
from typing import Any, Sequence

from ctypes import wintypes


if os.name == "nt":
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
else:  # pragma: no cover - exercised only on non-Windows hosts
    user32 = None
    kernel32 = None


INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x01000
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SW_RESTORE = 9
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

ULONG_PTR = wintypes.WPARAM


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]


_MOUSE_BUTTONS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}

_NAMED_KEYS = {
    "CTRL": 0x11,
    "CONTROL": 0x11,
    "SHIFT": 0x10,
    "ALT": 0x12,
    "WIN": 0x5B,
    "WINDOWS": 0x5B,
    "ENTER": 0x0D,
    "RETURN": 0x0D,
    "ESC": 0x1B,
    "ESCAPE": 0x1B,
    "SPACE": 0x20,
    "TAB": 0x09,
    "BACKSPACE": 0x08,
    "DELETE": 0x2E,
    "DEL": 0x2E,
    "INSERT": 0x2D,
    "HOME": 0x24,
    "END": 0x23,
    "PAGEUP": 0x21,
    "PAGEDOWN": 0x22,
    "UP": 0x26,
    "DOWN": 0x28,
    "LEFT": 0x25,
    "RIGHT": 0x27,
}
for _index in range(1, 13):
    _NAMED_KEYS[f"F{_index}"] = 0x6F + _index


class WindowsInputBackend:
    """Native Win32 input backend with no recurring-cost dependency."""

    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("EditGPT Hands currently requires Windows")
        self._configure_signatures()

    def _configure_signatures(self) -> None:
        assert user32 is not None and kernel32 is not None
        user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
        user32.SendInput.restype = wintypes.UINT
        user32.GetCursorPos.argtypes = (ctypes.POINTER(wintypes.POINT),)
        user32.GetCursorPos.restype = wintypes.BOOL
        user32.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
        user32.SetCursorPos.restype = wintypes.BOOL
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = (
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        )
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL

    def status(self) -> dict[str, Any]:
        left, top, width, height = self._virtual_screen()
        point = self._cursor_point()
        return {
            "platform": "windows",
            "backend": "win32_sendinput",
            "virtual_screen": {"left": left, "top": top, "width": width, "height": height},
            "cursor": {"x": point.x, "y": point.y},
        }

    def foreground_window(self) -> dict[str, Any]:
        assert user32 is not None
        hwnd = user32.GetForegroundWindow()
        return self._window_info(hwnd)

    def focus_window(self, process_name: str, title_contains: str | None = None) -> dict[str, Any]:
        assert user32 is not None
        expected = process_name.strip().lower()
        title_needle = title_contains.lower() if title_contains else None
        matches: list[dict[str, Any]] = []

        enum_proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        @enum_proc_type
        def callback(hwnd: int, _lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True
            info = self._window_info(hwnd)
            if str(info.get("process_name") or "").lower() != expected:
                return True
            title = str(info.get("title") or "")
            if title_needle and title_needle not in title.lower():
                return True
            if title:
                matches.append(info)
            return True

        user32.EnumWindows(callback, 0)
        if not matches:
            raise RuntimeError(f"no visible window found for process {process_name!r}")
        target = matches[0]
        hwnd = int(target["hwnd"])
        user32.ShowWindow(hwnd, SW_RESTORE)
        if not user32.SetForegroundWindow(hwnd):
            raise ctypes.WinError(ctypes.get_last_error())
        time.sleep(0.05)
        return self._window_info(hwnd)

    def move(self, x: int, y: int) -> None:
        assert user32 is not None
        self._validate_point(x, y)
        if not user32.SetCursorPos(int(x), int(y)):
            raise ctypes.WinError(ctypes.get_last_error())

    def click(self, button: str = "left", count: int = 1) -> None:
        normalized = button.lower()
        if normalized not in _MOUSE_BUTTONS:
            raise ValueError(f"unsupported mouse button: {button}")
        if count < 1 or count > 3:
            raise ValueError("click count must be between 1 and 3")
        down_flag, up_flag = _MOUSE_BUTTONS[normalized]
        for index in range(count):
            self._send_mouse(down_flag)
            self._send_mouse(up_flag)
            if index + 1 < count:
                time.sleep(0.06)

    def scroll(self, delta_x: int = 0, delta_y: int = 0) -> None:
        if delta_y:
            self._send_mouse(MOUSEEVENTF_WHEEL, mouse_data=delta_y)
        if delta_x:
            self._send_mouse(MOUSEEVENTF_HWHEEL, mouse_data=delta_x)

    def press_keys(self, keys: Sequence[str]) -> None:
        if not keys:
            raise ValueError("at least one key is required")
        virtual_keys = [self._virtual_key(key) for key in keys]
        for key in virtual_keys:
            self._send_key(key, key_up=False)
        for key in reversed(virtual_keys):
            self._send_key(key, key_up=True)

    def type_text(self, text: str) -> None:
        for unit in self._utf16_units(text):
            self._send_unicode(unit, key_up=False)
            self._send_unicode(unit, key_up=True)

    def drag(self, path: Sequence[tuple[int, int]], button: str = "left") -> None:
        normalized = button.lower()
        if normalized not in _MOUSE_BUTTONS:
            raise ValueError(f"unsupported mouse button: {button}")
        if len(path) < 2:
            raise ValueError("drag path requires at least two points")
        down_flag, up_flag = _MOUSE_BUTTONS[normalized]
        self.move(*path[0])
        self._send_mouse(down_flag)
        try:
            for point in path[1:]:
                self.move(*point)
                time.sleep(0.01)
        finally:
            self._send_mouse(up_flag)

    def _window_info(self, hwnd: int) -> dict[str, Any]:
        assert user32 is not None
        if not hwnd:
            return {"hwnd": 0, "title": "", "process_id": 0, "process_name": None}
        length = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(max(1, length + 1))
        user32.GetWindowTextW(hwnd, buffer, len(buffer))
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return {
            "hwnd": int(hwnd),
            "title": buffer.value,
            "process_id": int(pid.value),
            "process_name": self._process_name(int(pid.value)),
        }

    def _process_name(self, pid: int) -> str | None:
        assert kernel32 is not None
        if pid <= 0:
            return None
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return None
        try:
            capacity = wintypes.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(capacity.value)
            if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(capacity)):
                return None
            return Path(buffer.value).name
        finally:
            kernel32.CloseHandle(handle)

    def _cursor_point(self) -> wintypes.POINT:
        assert user32 is not None
        point = wintypes.POINT()
        if not user32.GetCursorPos(ctypes.byref(point)):
            raise ctypes.WinError(ctypes.get_last_error())
        return point

    def _virtual_screen(self) -> tuple[int, int, int, int]:
        assert user32 is not None
        return (
            int(user32.GetSystemMetrics(SM_XVIRTUALSCREEN)),
            int(user32.GetSystemMetrics(SM_YVIRTUALSCREEN)),
            int(user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)),
            int(user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)),
        )

    def _validate_point(self, x: int, y: int) -> None:
        left, top, width, height = self._virtual_screen()
        if x < left or y < top or x >= left + width or y >= top + height:
            raise ValueError(
                f"point ({x}, {y}) is outside virtual screen "
                f"[{left}, {top}, {left + width - 1}, {top + height - 1}]"
            )

    def _send_mouse(self, flags: int, *, mouse_data: int = 0) -> None:
        event = INPUT(
            type=INPUT_MOUSE,
            mi=MOUSEINPUT(
                dx=0,
                dy=0,
                mouseData=mouse_data & 0xFFFFFFFF,
                dwFlags=flags,
                time=0,
                dwExtraInfo=0,
            ),
        )
        self._send_input(event)

    def _send_key(self, virtual_key: int, *, key_up: bool) -> None:
        event = INPUT(
            type=INPUT_KEYBOARD,
            ki=KEYBDINPUT(
                wVk=virtual_key,
                wScan=0,
                dwFlags=KEYEVENTF_KEYUP if key_up else 0,
                time=0,
                dwExtraInfo=0,
            ),
        )
        self._send_input(event)

    def _send_unicode(self, unit: int, *, key_up: bool) -> None:
        flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if key_up else 0)
        event = INPUT(
            type=INPUT_KEYBOARD,
            ki=KEYBDINPUT(wVk=0, wScan=unit, dwFlags=flags, time=0, dwExtraInfo=0),
        )
        self._send_input(event)

    def _send_input(self, event: INPUT) -> None:
        assert user32 is not None
        sent = user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))
        if sent != 1:
            raise ctypes.WinError(ctypes.get_last_error())

    @staticmethod
    def _virtual_key(key: str) -> int:
        normalized = key.strip().upper().replace("_", "")
        if normalized in _NAMED_KEYS:
            return _NAMED_KEYS[normalized]
        if len(normalized) == 1 and (normalized.isalpha() or normalized.isdigit()):
            return ord(normalized)
        raise ValueError(f"unsupported key for chord/keypress: {key!r}; use type_text for text input")

    @staticmethod
    def _utf16_units(text: str) -> list[int]:
        encoded = text.encode("utf-16-le")
        return [int.from_bytes(encoded[index : index + 2], "little") for index in range(0, len(encoded), 2)]
