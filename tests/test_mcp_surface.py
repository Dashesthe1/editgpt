from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("mcp")

from editgpt.mcp_server import build_server


def test_mcp_exposes_core_eyes_tools() -> None:
    server = build_server()
    tools = asyncio.run(server.list_tools())
    names = {tool.name for tool in tools}
    assert {
        "eyes_start_live",
        "eyes_status",
        "eyes_stop_live",
        "eyes_latest_frame",
        "eyes_recent_frames",
        "eyes_frame",
        "eyes_motion_between",
    }.issubset(names)
