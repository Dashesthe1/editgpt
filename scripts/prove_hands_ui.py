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

EYES_URL = "http://127.0.0.1:8765/mcp"
HANDS_URL = "http://127.0.0.1:8766/mcp"


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


def _json_bool(text: str, key: str = "matches") -> bool:
    cleaned = text.strip().strip("`").strip()
    if cleaned.lower().startswith("json"):
        cleaned = cleaned[4:].lstrip()
    payload = json.loads(cleaned)
    return bool(payload.get(key))


async def _capture(eyes, hands, output: Path, name: str):
    focused = await hands.call_tool("hands_focus_after_effects", {})
    if focused.is_error:
        raise RuntimeError(f"could not focus AE: {focused.content}")
    await asyncio.sleep(0.12)
    result = await eyes.call_tool("eyes_latest_frame", {"max_width": 1280, "jpeg_quality": 92})
    if result.is_error:
        raise RuntimeError(f"Eyes capture failed: {result.content}")
    meta, image, jpeg = _frame_parts(result)
    (output / f"{name}.jpg").write_bytes(jpeg)
    return meta, image


def _map_target(meta: dict, hands_status: dict, target) -> tuple[int, int]:
    transform = CoordinateTransform.from_status(meta, hands_status)
    return transform.encoded_to_screen(target.x, target.y)


def _verify_text(qwen: LocalQwenVLClient, image: np.ndarray, prompt: str) -> tuple[bool, str]:
    obs = qwen.observe(
        image,
        prompt=prompt + ' Return only JSON: {"matches": true_or_false, "reason": "brief evidence"}',
        source="hands_ui_verification",
        max_tokens=120,
        max_width=image.shape[1],
        jpeg_quality=90,
    )
    return _json_bool(obs.text), obs.text


def _panel_change(a: np.ndarray, b: np.ndarray) -> dict[str, float]:
    h, w = a.shape[:2]
    y1 = int(h * 0.42)
    x1 = int(w * 0.80)
    aa = a[y1:h, x1:w].astype(np.int16)
    bb = b[y1:h, x1:w].astype(np.int16)
    delta = np.abs(bb - aa).mean(axis=2)
    return {
        "mean_abs_delta": float(delta.mean()),
        "changed_fraction": float((delta >= 10).mean()),
    }


def _timeline_playhead_x(image: np.ndarray) -> int:
    h, w = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    blue = cv2.inRange(hsv, np.array([85, 80, 120]), np.array([125, 255, 255])) > 0
    y1, y2 = int(h * 0.74), int(h * 0.92)
    x1, x2 = int(w * 0.42), int(w * 0.81)
    counts = blue[y1:y2, x1:x2].sum(axis=0)
    index = int(np.argmax(counts))
    if int(counts[index]) < 8:
        raise RuntimeError("could not visually locate the timeline current-time indicator")
    return x1 + index


async def prove() -> int:
    output = Path("artifacts/hands-ui-proof")
    output.mkdir(parents=True, exist_ok=True)
    proof: dict[str, object] = {}
    qwen = LocalQwenVLClient()
    if not qwen.health().get("ok"):
        print("ERROR: local Qwen is not ready")
        return 2

    async with Client(EYES_URL) as eyes, Client(HANDS_URL) as hands:
        armed = await hands.call_tool("hands_arm", {})
        if armed.is_error:
            print(armed.content)
            return 3
        started_eyes = False
        try:
            started = await eyes.call_tool("eyes_start_live", {"fps": 30, "buffer_seconds": 0.5})
            if started.is_error:
                print(started.content)
                return 4
            started_eyes = True

            # Type into Effects & Presets search, verify, then restore it to empty.
            search_meta, search_image = await _capture(eyes, hands, output, "search_before")
            search_target, search_obs = choose_pointer_target(
                search_image,
                instruction="Point to the center of the Effects & Presets search input field on the right side of After Effects.",
                client=qwen,
            )
            status = _structured(await hands.call_tool("hands_status", {}))
            search_screen = _map_target(search_meta, status, search_target)
            clicked = await hands.call_tool(
                "hands_click",
                {"x": search_screen[0], "y": search_screen[1], "button": "left", "count": 1},
            )
            if clicked.is_error:
                raise RuntimeError(f"search click failed: {clicked.content}")
            typed = await hands.call_tool("hands_type_text", {"text": "blur"})
            if typed.is_error:
                raise RuntimeError(f"typing failed: {typed.content}")
            await asyncio.sleep(0.4)
            _typed_meta, typed_image = await _capture(eyes, hands, output, "search_typed")
            typed_ok, typed_raw = _verify_text(
                qwen,
                typed_image,
                "Is the Effects & Presets search input visibly populated with the text 'blur'?",
            )
            if not typed_ok:
                raise RuntimeError(f"typed text was not visually verified: {typed_raw}")

            await hands.call_tool("hands_keypress", {"keys": ["CTRL", "A"]})
            await hands.call_tool("hands_keypress", {"keys": ["BACKSPACE"]})
            await asyncio.sleep(0.4)
            _cleared_meta, cleared_image = await _capture(eyes, hands, output, "search_cleared")
            cleared_ok, cleared_raw = _verify_text(
                qwen,
                cleared_image,
                "Is the Effects & Presets search input visibly empty with no typed query remaining?",
            )
            if not cleared_ok:
                raise RuntimeError(f"search clear was not visually verified: {cleared_raw}")

            # Scroll the Effects & Presets list and verify visible panel movement, then restore.
            scroll_meta, scroll_before = await _capture(eyes, hands, output, "scroll_before")
            scroll_target, scroll_obs = choose_pointer_target(
                scroll_before,
                instruction=(
                    "Point to an empty safe area inside the Effects & Presets category list on the right, "
                    "where mouse wheel scrolling will scroll that list."
                ),
                client=qwen,
            )
            status = _structured(await hands.call_tool("hands_status", {}))
            scroll_screen = _map_target(scroll_meta, status, scroll_target)
            scrolled = await hands.call_tool(
                "hands_scroll",
                {"scroll_y": 600, "x": scroll_screen[0], "y": scroll_screen[1]},
            )
            if scrolled.is_error:
                raise RuntimeError(f"scroll failed: {scrolled.content}")
            await asyncio.sleep(0.45)
            _after_meta, scroll_after = await _capture(eyes, hands, output, "scroll_after")
            scroll_change = _panel_change(scroll_before, scroll_after)
            if scroll_change["changed_fraction"] < 0.02:
                raise RuntimeError(f"scroll produced too little visible panel change: {scroll_change}")
            restored_scroll = await hands.call_tool(
                "hands_scroll",
                {"scroll_y": -600, "x": scroll_screen[0], "y": scroll_screen[1]},
            )
            if restored_scroll.is_error:
                raise RuntimeError(f"scroll restore failed: {restored_scroll.content}")
            await asyncio.sleep(0.45)
            _restore_meta, scroll_restored = await _capture(eyes, hands, output, "scroll_restored")
            scroll_restore_change = _panel_change(scroll_before, scroll_restored)

            # Drag the timeline current-time indicator, verify visible movement, then restore.
            drag_meta, drag_before = await _capture(eyes, hands, output, "drag_before")
            playhead, playhead_obs = choose_pointer_target(
                drag_before,
                instruction=(
                    "Point to the blue triangular current-time indicator playhead handle on the timeline "
                    "ruler near the bottom of After Effects, not the thin navigator bar above it."
                ),
                client=qwen,
            )
            status = _structured(await hands.call_tool("hands_status", {}))
            transform = CoordinateTransform.from_status(drag_meta, status)
            playhead_before_x = _timeline_playhead_x(drag_before)
            start_screen = transform.encoded_to_screen(playhead_before_x, playhead.y)
            end_encoded_x = min(drag_before.shape[1] - 220, playhead_before_x + 90)
            end_screen = transform.encoded_to_screen(end_encoded_x, playhead.y)
            mid_screen = ((start_screen[0] + end_screen[0]) // 2, start_screen[1])
            dragged = await hands.call_tool(
                "hands_computer_action",
                {"action": {"type": "drag", "path": [
                    {"x": start_screen[0], "y": start_screen[1]},
                    {"x": mid_screen[0], "y": mid_screen[1]},
                    {"x": end_screen[0], "y": end_screen[1]},
                ], "button": "left"}},
            )
            if dragged.is_error:
                raise RuntimeError(f"timeline playhead drag failed: {dragged.content}")
            await asyncio.sleep(0.45)
            moved_meta, moved_image = await _capture(eyes, hands, output, "drag_moved")
            playhead_moved_x = _timeline_playhead_x(moved_image)

            moved_transform = CoordinateTransform.from_status(
                moved_meta, _structured(await hands.call_tool("hands_status", {}))
            )
            moved_screen = moved_transform.encoded_to_screen(playhead_moved_x, playhead.y)
            restore_screen = moved_transform.encoded_to_screen(playhead_before_x, playhead.y)
            restore_mid = ((moved_screen[0] + restore_screen[0]) // 2, moved_screen[1])
            restored_drag = await hands.call_tool(
                "hands_computer_action",
                {"action": {"type": "drag", "path": [
                    {"x": moved_screen[0], "y": moved_screen[1]},
                    {"x": restore_mid[0], "y": restore_mid[1]},
                    {"x": restore_screen[0], "y": restore_screen[1]},
                ], "button": "left"}},
            )
            if restored_drag.is_error:
                raise RuntimeError(f"timeline playhead restore failed: {restored_drag.content}")
            await asyncio.sleep(0.45)
            _final_meta, final_image = await _capture(eyes, hands, output, "drag_restored")
            playhead_restored_x = _timeline_playhead_x(final_image)
            playhead_delta = playhead_moved_x - playhead_before_x
            restore_error = abs(playhead_restored_x - playhead_before_x)
            if playhead_delta < 40:
                raise RuntimeError(f"timeline playhead did not visibly move enough: delta={playhead_delta}")
            if restore_error > 12:
                raise RuntimeError(f"timeline playhead restore missed start: error={restore_error}")

            proof.update({
                "typing": {
                    "target": search_target.__dict__,
                    "semantic_raw": search_obs.as_dict(),
                    "screen_target": {"x": search_screen[0], "y": search_screen[1]},
                    "typed_verified": typed_ok,
                    "typed_raw": typed_raw,
                    "cleared_verified": cleared_ok,
                    "cleared_raw": cleared_raw,
                },
                "scroll": {
                    "target": scroll_target.__dict__,
                    "semantic_raw": scroll_obs.as_dict(),
                    "screen_target": {"x": scroll_screen[0], "y": scroll_screen[1]},
                    "change": scroll_change,
                    "restore_change": scroll_restore_change,
                },
                "drag": {
                    "target": playhead.__dict__,
                    "semantic_raw": playhead_obs.as_dict(),
                    "playhead_start_x": playhead_before_x,
                    "playhead_moved_x": playhead_moved_x,
                    "playhead_restored_x": playhead_restored_x,
                    "delta_x": playhead_delta,
                    "restore_error_x": restore_error,
                },
                "ok": True,
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
