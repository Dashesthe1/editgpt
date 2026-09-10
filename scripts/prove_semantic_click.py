from __future__ import annotations

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
        raise RuntimeError("OpenCV could not decode Eyes JPEG")
    return metadata, image, jpeg


def _verify_menu_state(qwen: LocalQwenVLClient, image: np.ndarray, *, expected_open: bool) -> tuple[bool, str]:
    state = "open with its dropdown visible" if expected_open else "closed with no File dropdown visible"
    observation = qwen.observe(
        image,
        prompt=(
            "Inspect only the visible Adobe After Effects UI. "
            f"Is the File menu {state}? Return only JSON: {{\"matches\": true_or_false, \"reason\": \"brief visible evidence\"}}"
        ),
        source="semantic_click_verification",
        max_tokens=120,
        max_width=image.shape[1],
        jpeg_quality=90,
    )
    text = observation.text.strip().strip("`").strip()
    if text.lower().startswith("json"):
        text = text[4:].lstrip()
    payload = json.loads(text)
    return bool(payload.get("matches")), observation.text


async def prove() -> int:
    output = Path("artifacts/semantic-click-proof")
    output.mkdir(parents=True, exist_ok=True)
    proof: dict[str, object] = {}
    qwen = LocalQwenVLClient()
    if not qwen.health().get("ok"):
        print("ERROR: local Qwen is not ready")
        return 2

    async with Client("http://127.0.0.1:8765/mcp") as eyes, Client("http://127.0.0.1:8766/mcp") as hands:
        await hands.call_tool("hands_arm", {})
        started_eyes = False
        try:
            focused = await hands.call_tool("hands_focus_after_effects", {})
            if focused.is_error:
                print(focused.content)
                return 3
            started = await eyes.call_tool("eyes_start_live", {"fps": 30, "buffer_seconds": 0.5})
            if started.is_error:
                print(started.content)
                return 4
            started_eyes = True
            await hands.call_tool("hands_focus_after_effects", {})
            await asyncio.sleep(0.15)

            before_result = await eyes.call_tool("eyes_latest_frame", {"max_width": 1280, "jpeg_quality": 92})
            before_meta, before_image, before_jpeg = _frame_parts(before_result)
            (output / "before.jpg").write_bytes(before_jpeg)
            target, target_observation = choose_pointer_target(
                before_image,
                instruction="Point to the File menu label in the top After Effects menu bar. Do not choose a dropdown item.",
                client=qwen,
                min_confidence=0.55,
            )
            hands_status = _structured(await hands.call_tool("hands_status", {}))
            transform = CoordinateTransform.from_status(before_meta, hands_status)
            screen_x, screen_y = transform.encoded_to_screen(target.x, target.y)
            moved = await hands.call_tool("hands_move", {"x": screen_x, "y": screen_y})
            if moved.is_error:
                print(moved.content)
                return 5
            clicked = await hands.call_tool("hands_click", {"x": screen_x, "y": screen_y, "button": "left", "count": 1})
            if clicked.is_error:
                print(clicked.content)
                return 6
            await asyncio.sleep(0.35)

            open_result = await eyes.call_tool("eyes_latest_frame", {"max_width": 1280, "jpeg_quality": 92})
            open_meta, open_image, open_jpeg = _frame_parts(open_result)
            (output / "menu_open.jpg").write_bytes(open_jpeg)
            menu_open_ok, open_raw = _verify_menu_state(qwen, open_image, expected_open=True)

            escaped = await hands.call_tool("hands_keypress", {"keys": ["ESC"]})
            if escaped.is_error:
                print(escaped.content)
                return 7
            await asyncio.sleep(0.35)
            closed_result = await eyes.call_tool("eyes_latest_frame", {"max_width": 1280, "jpeg_quality": 92})
            closed_meta, closed_image, closed_jpeg = _frame_parts(closed_result)
            (output / "menu_closed.jpg").write_bytes(closed_jpeg)
            menu_closed_ok, closed_raw = _verify_menu_state(qwen, closed_image, expected_open=False)

            proof.update({
                "target": target.__dict__,
                "target_raw": target_observation.as_dict(),
                "screen_target": {"x": screen_x, "y": screen_y},
                "before_frame_id": before_meta.get("frame_id"),
                "open_frame_id": open_meta.get("frame_id"),
                "closed_frame_id": closed_meta.get("frame_id"),
                "menu_open_verified": menu_open_ok,
                "menu_open_raw": open_raw,
                "menu_closed_verified": menu_closed_ok,
                "menu_closed_raw": closed_raw,
                "ok": bool(menu_open_ok and menu_closed_ok),
            })
        finally:
            if started_eyes:
                await eyes.call_tool("eyes_stop_live", {})
            await hands.call_tool("hands_disarm", {})

    (output / "proof.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")
    print(json.dumps(proof, indent=2))
    return 0 if proof.get("ok") else 8


if __name__ == "__main__":
    raise SystemExit(asyncio.run(prove()))
