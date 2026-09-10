from __future__ import annotations

import argparse
import asyncio
import base64
import json
from pathlib import Path

import cv2
import numpy as np
from mcp import Client

from editgpt.controller.coordinates import CoordinateTransform
from editgpt.controller.semantic_pointer import choose_pointer_target
from editgpt.eyes.semantic import LocalQwenVLClient


def _structured(result) -> dict:
    value = result.structured_content or {}
    return value if isinstance(value, dict) else {}


def _frame_parts(result) -> tuple[dict, np.ndarray, bytes]:
    metadata = None
    jpeg = None
    for block in result.content:
        if getattr(block, "type", None) == "text":
            try:
                value = json.loads(getattr(block, "text", ""))
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and "frame_id" in value:
                metadata = value
        elif getattr(block, "type", None) == "image":
            jpeg = base64.b64decode(block.data)
    if metadata is None or jpeg is None:
        raise RuntimeError("Eyes frame did not contain metadata and JPEG evidence")
    image = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError("OpenCV could not decode the Eyes JPEG")
    return metadata, image, jpeg


async def prove(eyes_url: str, hands_url: str) -> int:
    output = Path("artifacts/semantic-pointer-proof")
    output.mkdir(parents=True, exist_ok=True)
    proof: dict[str, object] = {"eyes_url": eyes_url, "hands_url": hands_url}
    qwen = LocalQwenVLClient()
    health = qwen.health()
    proof["semantic_server"] = health
    if not health.get("ok"):
        print(json.dumps(proof, indent=2))
        return 2

    async with Client(eyes_url) as eyes, Client(hands_url) as hands:
        await hands.call_tool("hands_arm", {})
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
            await hands.call_tool("hands_focus_after_effects", {})
            await asyncio.sleep(0.15)

            frame_result = await eyes.call_tool("eyes_latest_frame", {"max_width": 1280, "jpeg_quality": 92})
            if frame_result.is_error:
                print(frame_result.content)
                return 5
            frame_meta, image, jpeg = _frame_parts(frame_result)
            (output / "source.jpg").write_bytes(jpeg)

            target, observation = choose_pointer_target(
                image,
                instruction="Point to the File menu label in the top After Effects menu bar. Do not choose any item inside a dropdown.",
                client=qwen,
                min_confidence=0.55,
            )
            hands_before = _structured(await hands.call_tool("hands_status", {}))
            transform = CoordinateTransform.from_status(frame_meta, hands_before)
            screen_target = transform.encoded_to_screen(target.x, target.y)
            moved = await hands.call_tool("hands_move", {"x": screen_target[0], "y": screen_target[1]})
            if moved.is_error:
                print(moved.content)
                return 6
            await asyncio.sleep(0.2)
            hands_after = _structured(await hands.call_tool("hands_status", {}))
            cursor = ((hands_after.get("backend") or {}).get("cursor") or {})
            cursor_ok = (cursor.get("x"), cursor.get("y")) == screen_target
            after_result = await eyes.call_tool("eyes_latest_frame", {"max_width": 1280, "jpeg_quality": 85})
            after_meta, _after_image, _after_jpeg = _frame_parts(after_result)

            proof.update({
                "frame": frame_meta,
                "semantic_target": target.__dict__,
                "semantic_raw": observation.as_dict(),
                "screen_target": {"x": screen_target[0], "y": screen_target[1]},
                "hands_after": hands_after,
                "after_frame": after_meta,
                "cursor_verified": cursor_ok,
                "ok": bool(cursor_ok and after_meta.get("frame_id")),
            })
        finally:
            if started_eyes:
                await eyes.call_tool("eyes_stop_live", {})
            await hands.call_tool("hands_disarm", {})
    (output / "proof.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")
    print(json.dumps(proof, indent=2))
    return 0 if proof.get("ok") else 7


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eyes-url", default="http://127.0.0.1:8765/mcp")
    parser.add_argument("--hands-url", default="http://127.0.0.1:8766/mcp")
    args = parser.parse_args()
    return asyncio.run(prove(args.eyes_url, args.hands_url))


if __name__ == "__main__":
    raise SystemExit(main())
