from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path

import cv2
import numpy as np
from mcp import Client

from editgpt.controller.coordinates import CoordinateTransform
from editgpt.controller.planner import verify_visible_state
from editgpt.controller.semantic_pointer import choose_pointer_target
from editgpt.eyes.semantic import LocalQwenVLClient

EYES_URL = "http://127.0.0.1:8765/mcp"
HANDS_URL = "http://127.0.0.1:8766/mcp"


def _structured(result):
    value = result.structured_content or {}
    return value if isinstance(value, dict) else {}


def _frame_parts(result):
    meta = None
    data = None
    for block in result.content:
        if getattr(block, "type", None) == "text":
            try:
                value = json.loads(block.text)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and "frame_id" in value:
                meta = value
        elif getattr(block, "type", None) == "image":
            data = base64.b64decode(block.data)
    if meta is None or data is None:
        raise RuntimeError("Eyes frame evidence was incomplete")
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError("Eyes JPEG decode failed")
    return meta, image


def _path(a: tuple[int, int], b: tuple[int, int], points: int = 12):
    return [
        {"x": round(a[0] + (b[0] - a[0]) * i / points),
         "y": round(a[1] + (b[1] - a[1]) * i / points)}
        for i in range(points + 1)
    ]


async def _capture(eyes, hands):
    focused = await hands.call_tool("hands_focus_after_effects", {})
    if focused.is_error:
        raise RuntimeError(f"could not focus AE: {focused.content}")
    await asyncio.sleep(0.15)
    frame = await eyes.call_tool("eyes_latest_frame", {"max_width": 1280, "jpeg_quality": 92})
    if frame.is_error:
        raise RuntimeError(f"Eyes frame failed: {frame.content}")
    return _frame_parts(frame)


async def prove() -> int:
    output = Path("artifacts/drag-proof")
    output.mkdir(parents=True, exist_ok=True)
    qwen = LocalQwenVLClient()
    proof: dict[str, object] = {}

    async with Client(EYES_URL) as eyes, Client(HANDS_URL) as hands:
        armed = await hands.call_tool("hands_arm", {})
        if armed.is_error:
            return 2
        started_here = False
        try:
            started = await eyes.call_tool("eyes_start_live", {"fps": 30, "buffer_seconds": 0.8})
            if started.is_error:
                return 3
            started_here = bool(_structured(started).get("started", False))
            meta, image = await _capture(eyes, hands)
            source, source_obs = choose_pointer_target(
                image,
                instruction="Point to the blue current-time indicator/playhead handle in the bottom Timeline panel ruler.",
                client=qwen,
                min_confidence=0.60,
            )
            destination, destination_obs = choose_pointer_target(
                image,
                instruction="Point to the 02s ruler mark in the bottom Timeline panel, on the same ruler where the blue playhead moves.",
                client=qwen,
                min_confidence=0.60,
            )

            status = _structured(await hands.call_tool("hands_status", {}))
            transform = CoordinateTransform.from_status(meta, status)
            src_screen = transform.encoded_to_screen(source.x, source.y)
            dst_screen = transform.encoded_to_screen(destination.x, destination.y)
            proof.update({
                "before_frame_id": meta.get("frame_id"),
                "source": source.__dict__,
                "source_semantic": source_obs.as_dict(),
                "destination": destination.__dict__,
                "destination_semantic": destination_obs.as_dict(),
                "source_screen": {"x": src_screen[0], "y": src_screen[1]},
                "destination_screen": {"x": dst_screen[0], "y": dst_screen[1]},
            })

            drag = await hands.call_tool(
                "hands_computer_action",
                {"action": {"type": "drag", "button": "left", "path": _path(src_screen, dst_screen)}},
            )
            if drag.is_error:
                proof["drag_error"] = str(drag.content)
                return 4
            await asyncio.sleep(0.4)
            post_meta, post_image = await _capture(eyes, hands)
            verified, reason, verification = verify_visible_state(
                post_image,
                statement="The blue current-time indicator/playhead in the bottom Timeline panel is positioned at approximately the 02s ruler mark.",
                client=qwen,
                source="drag_proof_verification",
            )
            proof.update({
                "after_frame_id": post_meta.get("frame_id"),
                "verified": verified,
                "verification_reason": reason,
                "verification": verification.as_dict(),
            })

            restore = await hands.call_tool(
                "hands_computer_action",
                {"action": {"type": "drag", "button": "left", "path": _path(dst_screen, src_screen)}},
            )
            proof["restore_ok"] = not restore.is_error
            proof["ok"] = bool(verified and not restore.is_error)
        finally:
            if started_here:
                await eyes.call_tool("eyes_stop_live", {})
            await hands.call_tool("hands_disarm", {})

    (output / "proof.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")
    print(json.dumps(proof, indent=2))
    return 0 if proof.get("ok") else 5


if __name__ == "__main__":
    raise SystemExit(asyncio.run(prove()))
