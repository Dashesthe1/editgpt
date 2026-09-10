from __future__ import annotations

from editgpt.hands.windows import WindowsInputBackend


def test_after_effects_oem_shortcut_keys_are_supported() -> None:
    expected = {
        "[": 0xDB, "]": 0xDD, "/": 0xBF, "\\": 0xDC,
        ";": 0xBA, "'": 0xDE, "-": 0xBD, "=": 0xBB,
        ",": 0xBC, ".": 0xBE, "`": 0xC0,
    }
    for key, virtual_key in expected.items():
        assert WindowsInputBackend._virtual_key(key) == virtual_key


def test_named_after_effects_oem_aliases_are_supported() -> None:
    assert WindowsInputBackend._virtual_key("LBRACKET") == 0xDB
    assert WindowsInputBackend._virtual_key("RBRACKET") == 0xDD
    assert WindowsInputBackend._virtual_key("SLASH") == 0xBF
    assert WindowsInputBackend._virtual_key("BACKSLASH") == 0xDC
    assert WindowsInputBackend._virtual_key("SEMICOLON") == 0xBA
    assert WindowsInputBackend._virtual_key("APOSTROPHE") == 0xDE
