from __future__ import annotations

import argparse
from typing import Any

from .hands.service import HandsService
from .hands.windows import WindowsInputBackend

_SERVICE: HandsService | None = None


def _service() -> HandsService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = HandsService(WindowsInputBackend())
    return _SERVICE


def build_server():
    try:
        from mcp.server.mcpserver import MCPServer
    except ImportError as exc:
        raise RuntimeError("MCP SDK v2 is required; install editgpt[mcp].") from exc

    mcp = MCPServer("EditGPT Hands")

    @mcp.tool()
    def hands_status() -> dict[str, Any]:
        """Return Hands arming state, foreground-window guard state, cursor, and display geometry."""
        return _service().status()

    @mcp.tool()
    def hands_arm(allowed_processes: list[str] | None = None) -> dict[str, Any]:
        """Arm write-capable desktop input. Defaults to AfterFX.exe only."""
        return _service().arm(allowed_processes)

    @mcp.tool()
    def hands_disarm() -> dict[str, Any]:
        """Immediately disable EditGPT mouse and keyboard actions."""
        return _service().disarm()

    @mcp.tool()
    def hands_focus_after_effects(title_contains: str | None = None) -> dict[str, Any]:
        """Bring an allowlisted After Effects window to the foreground after Hands is armed."""
        return _service().focus_target("AfterFX.exe", title_contains=title_contains)

    @mcp.tool()
    def hands_computer_action(action: dict[str, Any]) -> dict[str, Any]:
        """Execute one guarded computer-use-style action.

        Supported action.type values: click, double_click, move, scroll,
        keypress/key_press, type, drag, wait. Eyes supplies screenshots.
        """
        return _service().execute(action)

    @mcp.tool()
    def hands_move(x: int, y: int) -> dict[str, Any]:
        """Move the cursor to absolute virtual-screen coordinates."""
        return _service().execute({"type": "move", "x": x, "y": y})

    @mcp.tool()
    def hands_click(x: int, y: int, button: str = "left", count: int = 1) -> dict[str, Any]:
        """Click an absolute screen coordinate once or twice."""
        if count not in (1, 2):
            raise ValueError("count must be 1 or 2")
        return _service().execute(
            {
                "type": "double_click" if count == 2 else "click",
                "x": x,
                "y": y,
                "button": button,
            }
        )

    @mcp.tool()
    def hands_scroll(
        scroll_x: int = 0,
        scroll_y: int = 0,
        x: int | None = None,
        y: int | None = None,
    ) -> dict[str, Any]:
        """Send horizontal/vertical wheel deltas, optionally after moving to x/y."""
        action: dict[str, Any] = {"type": "scroll", "scroll_x": scroll_x, "scroll_y": scroll_y}
        if (x is None) != (y is None):
            raise ValueError("x and y must be provided together")
        if x is not None and y is not None:
            action.update({"x": x, "y": y})
        return _service().execute(action)

    @mcp.tool()
    def hands_keypress(keys: list[str]) -> dict[str, Any]:
        """Press a key or chord such as ['CTRL', 'SHIFT', 'K']."""
        return _service().execute({"type": "keypress", "keys": keys})

    @mcp.tool()
    def hands_type_text(text: str) -> dict[str, Any]:
        """Type Unicode text into the foreground allowlisted application."""
        return _service().execute({"type": "type", "text": text})

    return mcp


mcp = build_server()


def main() -> int:
    parser = argparse.ArgumentParser(prog="editgpt-hands-mcp")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="streamable-http",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument(
        "--allow-nonlocal-bind",
        action="store_true",
        help="explicitly allow binding the write-capable Hands MCP beyond loopback",
    )
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run("stdio")
        return 0

    loopback_hosts = {"127.0.0.1", "localhost", "::1"}
    if args.host not in loopback_hosts and not args.allow_nonlocal_bind:
        raise SystemExit(
            "Refusing a non-loopback bind for the write-capable Hands MCP. "
            "Use --allow-nonlocal-bind only behind an explicitly protected authenticated route."
        )

    mcp.run(
        "streamable-http",
        host=args.host,
        port=args.port,
        json_response=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
