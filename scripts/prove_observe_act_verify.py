from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from mcp import Client

from editgpt.controller.coordinates import CoordinateTransform


def _structured(result) -> dict:
    value = result.structured_content or {}
    return value if isinstance(value, dict) else {}


def _text_json(result) -> dict:
    for block in result.content:
        if getattr(block, "type", None) == "text":
            text = getattr(block, "text", "")
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and "frame_id" in value:
                return value
    raise RuntimeError("Eyes frame result did not contain JSON metadata")


async def prove(eyes_url: str, hands_url: str) -> int:
    output = Path("artifacts/observe-act-verify-proof")
    output.mkdir(parents=True, exist_ok=True)
    proof: dict[str, object] = {"eyes_url": eyes_url, "hands_url": hands_url}
    async with Client(eyes_url) as eyes, Client(hands_url) as hands:
        armed = await hands.call_tool("hands_arm", {})
        if armed.is_error:
            print(armed.content)
            return 2
        started_eyes = False
        try:
            focused = await hands.call_tool("hands_focus_after_effects", {})
            if focused.is_error:
                print(focused.content)
                return 3
            proof["focus"] = _structured(focused)

            started = await eyes.call_tool("eyes_start_live", {"fps": 30, "buffer_seconds": 0.5})
            if started.is_error:
                print(started.content)
                return 4
            started_eyes = True
            await asyncio.sleep(0.5)

            before_result = await eyes.call_tool("eyes_latest_frame", {"max_width": 1280, "jpeg_quality": 85})
            if before_result.is_error:
                print(before_result.content)
                return 5
            before = _text_json(before_result)
            hands_before = _structured(await hands.call_tool("hands_status", {}))
            transform = CoordinateTransform.from_status(before, hands_before)
            target_encoded = (transform.encoded_width // 2, transform.encoded_height // 2)
            target_screen = transform.encoded_to_screen(*target_encoded)
            moved = await hands.call_tool("hands_move", {"x": target_screen[0], "y": target_screen[1]})
            if moved.is_error:
                print(moved.content)
                return 6
            await asyncio.sleep(0.15)

            hands_after = _structured(await hands.call_tool("hands_status", {}))
            cursor = ((hands_after.get("backend") or {}).get("cursor") or {})
            cursor_ok = (cursor.get("x"), cursor.get("y")) == target_screen
            after_result = await eyes.call_tool("eyes_latest_frame", {"max_width": 1280, "jpeg_quality": 85})
            if after_result.is_error:
                print(after_result.content)
                return 7
            after = _text_json(after_result)

            proof.update({
                "before_frame": before,
                "encoded_target": {"x": target_encoded[0], "y": target_encoded[1]},
                "screen_target": {"x": target_screen[0], "y": target_screen[1]},
                "hands_after": hands_after,
                "after_frame": after,
                "cursor_verified": cursor_ok,
                "eyes_healthy_after_action": isinstance(after.get("frame_id"), int),
            })
            proof["ok"] = bool(cursor_ok and proof["eyes_healthy_after_action"])
        finally:
            if started_eyes:
                await eyes.call_tool("eyes_stop_live", {})
            await hands.call_tool("hands_disarm", {})
    (output / "proof.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")
    print(json.dumps(proof, indent=2))
    return 0 if proof.get("ok") else 8


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eyes-url", default="http://127.0.0.1:8765/mcp")
    parser.add_argument("--hands-url", default="http://127.0.0.1:8766/mcp")
    args = parser.parse_args()
    return asyncio.run(prove(args.eyes_url, args.hands_url))


if __name__ == "__main__":
    raise SystemExit(main())
