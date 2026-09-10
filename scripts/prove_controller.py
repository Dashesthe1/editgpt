from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from mcp import Client

from editgpt.controller.live_loop import LiveController

DEFAULT_GOAL = (
    "In Adobe After Effects, first open the File menu. After the File dropdown is visibly open, "
    "click Edit in the top menu bar so the Edit dropdown becomes visibly open. Finish with the "
    "Edit dropdown open. Do not modify project content."
)


async def _cleanup_menu(hands_url: str) -> None:
    async with Client(hands_url) as hands:
        armed = await hands.call_tool("hands_arm", {})
        if armed.is_error:
            return
        try:
            focused = await hands.call_tool("hands_focus_after_effects", {})
            if not focused.is_error:
                await hands.call_tool("hands_keypress", {"keys": ["ESC"]})
        finally:
            await hands.call_tool("hands_disarm", {})


async def prove(goal: str, max_steps: int) -> int:
    output = Path("artifacts/controller-proof")
    output.mkdir(parents=True, exist_ok=True)
    controller = LiveController(safe_mode=True, max_steps=max_steps)
    try:
        result = await controller.run(goal)
    finally:
        await _cleanup_menu(controller.hands_url)

    payload = result.as_dict()
    (output / "proof.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if result.ok else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Prove the generalized EditGPT closed-loop controller.")
    parser.add_argument("--goal", default=DEFAULT_GOAL)
    parser.add_argument("--max-steps", type=int, default=5)
    args = parser.parse_args()
    return asyncio.run(prove(args.goal, args.max_steps))


if __name__ == "__main__":
    raise SystemExit(main())
