from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("mcp")

from editgpt.hands_mcp_server import build_server


def test_mcp_exposes_guarded_hands_tools() -> None:
    server = build_server()
    tools = asyncio.run(server.list_tools())
    names = {tool.name for tool in tools}
    assert {
        "hands_status",
        "hands_arm",
        "hands_disarm",
        "hands_focus_after_effects",
        "hands_computer_action",
        "hands_move",
        "hands_click",
        "hands_scroll",
        "hands_keypress",
        "hands_type_text",
    }.issubset(names)
