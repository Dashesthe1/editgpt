from __future__ import annotations

import argparse
import asyncio
import base64
import json
import socket
from pathlib import Path
from urllib.parse import urlsplit

from mcp import Client


def _listener_available(url: str, timeout_s: float = 1.0) -> bool:
    parsed = urlsplit(url)
    host = parsed.hostname
    if not host:
        return False
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


async def prove(url: str, fps: int, seconds: float, delay: float) -> int:
    output = Path("artifacts/eyes-mcp-proof")
    output.mkdir(parents=True, exist_ok=True)

    print(f"Connecting to {url}")
    if not _listener_available(url):
        print("ERROR: No EditGPT Eyes MCP server is listening at that address.")
        print("Start it in a separate PowerShell window and leave that window running:")
        print(r"  .\.venv\Scripts\editgpt-eyes-mcp.exe --transport streamable-http --host 127.0.0.1 --port 8765")
        return 8

    async with Client(url) as client:
        tools = await client.list_tools()
        tool_names = sorted(tool.name for tool in tools.tools)
        required = {
            "eyes_start_live",
            "eyes_status",
            "eyes_stop_live",
            "eyes_latest_frame",
            "eyes_recent_frames",
            "eyes_frame",
            "eyes_motion_between",
        }
        missing = sorted(required.difference(tool_names))
        print(json.dumps({"tools": tool_names, "missing_required_tools": missing}, indent=2))
        if missing:
            return 2

        print(f"MCP capture starts in {delay:g} seconds. Switch to After Effects and play the Composition preview now.")
        await asyncio.sleep(delay)

        started = await client.call_tool(
            "eyes_start_live",
            {"fps": fps, "buffer_seconds": 0.5},
        )
        if started.is_error:
            print(started.content)
            return 3

        await asyncio.sleep(seconds)

        status_result = await client.call_tool("eyes_status", {})
        if status_result.is_error:
            print(status_result.content)
            return 4
        status = status_result.structured_content or {}
        print(json.dumps(status, indent=2))
        (output / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")

        frame_result = await client.call_tool(
            "eyes_latest_frame",
            {"max_width": 1280, "jpeg_quality": 90},
        )
        if frame_result.is_error:
            print(frame_result.content)
            return 5

        image_saved = False
        for block in frame_result.content:
            if getattr(block, "type", None) == "image":
                data = base64.b64decode(block.data)
                (output / "latest.jpg").write_bytes(data)
                image_saved = True
                break

        stopped = await client.call_tool("eyes_stop_live", {})
        if stopped.is_error:
            print(stopped.content)
            return 6

    result = {
        "ok": bool(status.get("captured_frames", 0) > 0 and image_saved),
        "captured_frames": status.get("captured_frames"),
        "observed_fps": status.get("observed_fps"),
        "latest_image_saved": image_saved,
        "output_dir": str(output),
    }
    (output / "proof.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 7


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8765/mcp")
    parser.add_argument("--fps", type=int, default=60)
    parser.add_argument("--seconds", type=float, default=3.0)
    parser.add_argument("--delay", type=float, default=5.0)
    args = parser.parse_args()
    return asyncio.run(prove(args.url, args.fps, args.seconds, args.delay))


if __name__ == "__main__":
    raise SystemExit(main())
