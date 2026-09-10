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


def test_mcp_exposes_read_only_source_evidence_tools() -> None:
    server = build_server()
    tools = asyncio.run(server.list_tools())
    names = {tool.name for tool in tools}
    assert {
        "eyes_source_health",
        "eyes_source_open",
        "eyes_source_info",
        "eyes_source_frame",
        "eyes_source_frames",
        "eyes_source_index_at_time",
        "eyes_source_close",
    }.issubset(names)


def test_mcp_exposes_temporal_event_tools() -> None:
    server = build_server()
    tools = asyncio.run(server.list_tools())
    names = {tool.name for tool in tools}
    assert {"eyes_source_temporal_profile", "eyes_source_find_event"}.issubset(names)
