from __future__ import annotations

from editgpt.hands.windows import (
    WHEEL_DELTA,
    WindowsInputBackend,
    _MOUSE_BUTTONS,
)


def test_openai_click_button_vocabulary_is_supported() -> None:
    assert {"left", "right", "wheel", "back", "forward"}.issubset(_MOUSE_BUTTONS)


def test_vertical_model_scroll_is_converted_to_win32_direction() -> None:
    assert WindowsInputBackend._pixel_scroll_to_wheel(120, invert=True) == -WHEEL_DELTA
    assert WindowsInputBackend._pixel_scroll_to_wheel(-120, invert=True) == WHEEL_DELTA


def test_small_nonzero_scroll_still_emits_one_native_notch() -> None:
    assert WindowsInputBackend._pixel_scroll_to_wheel(1, invert=True) == -WHEEL_DELTA
    assert WindowsInputBackend._pixel_scroll_to_wheel(-1, invert=True) == WHEEL_DELTA


def test_horizontal_scroll_preserves_model_direction() -> None:
    assert WindowsInputBackend._pixel_scroll_to_wheel(240, invert=False) == 2 * WHEEL_DELTA
    assert WindowsInputBackend._pixel_scroll_to_wheel(-240, invert=False) == -2 * WHEEL_DELTA
