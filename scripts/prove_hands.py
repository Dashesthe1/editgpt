from __future__ import annotations

import argparse
import asyncio
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


def _content(result) -> dict:
    value = result.structured_content or {}
    return value if isinstance(value, dict) else {}


async def prove(url: str) -> int:
    output = Path("artifacts/hands-mcp-proof")
    output.mkdir(parents=True, exist_ok=True)

    if not _listener_available(url):
        print(f"ERROR: No EditGPT Hands MCP is listening at {url}")
        return 8

    proof: dict[str, object] = {"url": url}
    async with Client(url) as client:
        tools = await client.list_tools()
        tool_names = sorted(tool.name for tool in tools.tools)
        required = {
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
        }
        missing = sorted(required.difference(tool_names))
        proof["tools"] = tool_names
        proof["missing_required_tools"] = missing
        if missing:
            print(json.dumps(proof, indent=2))
            return 2

        initial = await client.call_tool("hands_status", {})
        if initial.is_error:
            print(initial.content)
            return 3
        proof["initial_status"] = _content(initial)

        armed = await client.call_tool("hands_arm", {})
        if armed.is_error:
            print(armed.content)
            return 4

        try:
            focused = await client.call_tool("hands_focus_after_effects", {})
            if focused.is_error:
                print(focused.content)
                return 5
            proof["focus"] = _content(focused)

            status_result = await client.call_tool("hands_status", {})
            if status_result.is_error:
                print(status_result.content)
                return 6
            status = _content(status_result)
            proof["armed_status"] = status

            backend = status.get("backend") if isinstance(status.get("backend"), dict) else {}
            cursor = backend.get("cursor") if isinstance(backend.get("cursor"), dict) else {}
            x = cursor.get("x")
            y = cursor.get("y")
            if not isinstance(x, int) or not isinstance(y, int):
                print("ERROR: Hands status did not report integer cursor coordinates")
                return 7

            # Non-destructive write-path proof: move to the exact current coordinate.
            moved = await client.call_tool("hands_move", {"x": x, "y": y})
            if moved.is_error:
                print(moved.content)
                return 9
            proof["noop_move"] = _content(moved)
        finally:
            disarmed = await client.call_tool("hands_disarm", {})
            proof["disarm"] = _content(disarmed)

    proof["ok"] = True
    (output / "proof.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")
    print(json.dumps(proof, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8766/mcp")
    args = parser.parse_args()
    return asyncio.run(prove(args.url))


if __name__ == "__main__":
    raise SystemExit(main())
