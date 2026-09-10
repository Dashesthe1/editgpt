from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
from mcp import Client

from editgpt.controller.coordinates import CoordinateTransform
from editgpt.controller.planner import PlannedAction, choose_next_action, verify_visible_state
from editgpt.controller.policy import TaskPolicy
from editgpt.controller.semantic_pointer import choose_pointer_target
from editgpt.eyes.semantic import LocalQwenVLClient


@dataclass(frozen=True)
class LiveControllerResult:
    ok: bool
    status: str
    goal: str
    steps: tuple[dict[str, Any], ...]
    final_frame_id: int | None
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "goal": self.goal,
            "steps": list(self.steps),
            "final_frame_id": self.final_frame_id,
            "detail": self.detail,
        }


def _structured(result) -> dict[str, Any]:
    value = result.structured_content or {}
    return value if isinstance(value, dict) else {}


def _frame_parts(result) -> tuple[dict[str, Any], np.ndarray]:
    metadata: dict[str, Any] | None = None
    jpeg: bytes | None = None
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
    return metadata, image


class StaleObservationError(RuntimeError):
    pass


def _target_patch_change(a: np.ndarray, b: np.ndarray, bbox: tuple[int, int, int, int]) -> float:
    if a.shape != b.shape:
        return 1.0
    x1, y1, x2, y2 = bbox
    pad = 12
    x1 = max(0, x1 - pad); y1 = max(0, y1 - pad)
    x2 = min(a.shape[1], x2 + pad); y2 = min(a.shape[0], y2 + pad)
    aa = a[y1:y2, x1:x2].astype(np.int16)
    bb = b[y1:y2, x1:x2].astype(np.int16)
    if aa.size == 0:
        return 1.0
    delta = np.abs(bb - aa).mean(axis=2)
    return float((delta >= 15).mean())


class LiveController:
    """Closed-loop local controller over the paired Eyes and Hands MCPs."""

    def __init__(
        self,
        *,
        eyes_url: str = "http://127.0.0.1:8765/mcp",
        hands_url: str = "http://127.0.0.1:8766/mcp",
        qwen: LocalQwenVLClient | None = None,
        safe_mode: bool = True,
        max_steps: int = 6,
        policy: TaskPolicy | None = None,
    ) -> None:
        if max_steps < 1 or max_steps > 12:
            raise ValueError("max_steps must be between 1 and 12")
        self.eyes_url = eyes_url
        self.hands_url = hands_url
        self.qwen = qwen or LocalQwenVLClient()
        self.safe_mode = safe_mode
        self.max_steps = max_steps
        self.policy = policy or (TaskPolicy.ui_proof() if safe_mode else TaskPolicy.editing())

    async def _capture_after_effects(self, eyes, hands) -> tuple[dict[str, Any], np.ndarray]:
        focused = await hands.call_tool("hands_focus_after_effects", {})
        if focused.is_error:
            raise RuntimeError(f"could not focus After Effects: {focused.content}")
        await asyncio.sleep(0.12)
        frame_result = await eyes.call_tool(
            "eyes_latest_frame",
            {"max_width": 1280, "jpeg_quality": 92},
        )
        if frame_result.is_error:
            raise RuntimeError(f"Eyes capture failed: {frame_result.content}")
        return _frame_parts(frame_result)

    async def _execute_plan(
        self,
        *,
        plan: PlannedAction,
        frame_meta: dict[str, Any],
        image: np.ndarray,
        eyes,
        hands,
    ) -> dict[str, Any]:
        action_type = plan.action_type
        if action_type is None:
            raise ValueError("cannot execute a plan without an action")
        target_record: dict[str, Any] | None = None
        screen_target: tuple[int, int] | None = None
        screen_destination: tuple[int, int] | None = None

        if action_type in {"click", "double_click", "move", "scroll", "drag"}:
            assert plan.target is not None
            ground_meta, ground_image = await self._capture_after_effects(eyes, hands)
            target, observation = choose_pointer_target(
                ground_image,
                instruction=f"Point to this exact visible After Effects UI target: {plan.target}",
                client=self.qwen,
                min_confidence=0.60,
            )
            destination = None
            destination_observation = None
            if action_type == "drag":
                assert plan.destination is not None
                destination, destination_observation = choose_pointer_target(
                    ground_image,
                    instruction=f"Point to this exact visible After Effects drag destination: {plan.destination}",
                    client=self.qwen,
                    min_confidence=0.60,
                )
            if not await self._foreground_is_after_effects(hands):
                raise StaleObservationError("After Effects lost foreground during target grounding")
            latest_result = await eyes.call_tool(
                "eyes_latest_frame", {"max_width": 1280, "jpeg_quality": 92}
            )
            if latest_result.is_error:
                raise RuntimeError(f"freshness capture failed: {latest_result.content}")
            action_meta, action_image = _frame_parts(latest_result)
            if ground_meta.get("geometry") != action_meta.get("geometry"):
                raise StaleObservationError("Eyes geometry changed between grounding and action")
            patch_change = 0.0
            if target.bbox_pixels is not None:
                patch_change = _target_patch_change(ground_image, action_image, target.bbox_pixels)
                if patch_change > 0.12:
                    raise StaleObservationError(
                        f"target changed after grounding (changed_fraction={patch_change:.3f})"
                    )
            hands_status = _structured(await hands.call_tool("hands_status", {}))
            transform = CoordinateTransform.from_status(action_meta, hands_status)
            screen_target = transform.encoded_to_screen(target.x, target.y)
            if destination is not None:
                screen_destination = transform.encoded_to_screen(destination.x, destination.y)
            target_record = {
                "semantic_target": target.__dict__,
                "grounding": observation.as_dict(),
                "semantic_destination": None if destination is None else destination.__dict__,
                "destination_grounding": None if destination_observation is None else destination_observation.as_dict(),
                "grounded_frame_id": ground_meta.get("frame_id"),
                "action_frame_id": action_meta.get("frame_id"),
                "target_patch_changed_fraction": patch_change,
                "screen": {"x": screen_target[0], "y": screen_target[1]},
                "screen_destination": None if screen_destination is None else {"x": screen_destination[0], "y": screen_destination[1]},
            }

        if action_type in {"click", "double_click"}:
            assert screen_target is not None
            result = await hands.call_tool(
                "hands_click",
                {
                    "x": screen_target[0],
                    "y": screen_target[1],
                    "button": "left",
                    "count": 2 if action_type == "double_click" else 1,
                },
            )
        elif action_type == "move":
            assert screen_target is not None
            result = await hands.call_tool(
                "hands_move", {"x": screen_target[0], "y": screen_target[1]}
            )
        elif action_type == "scroll":
            assert screen_target is not None
            result = await hands.call_tool(
                "hands_scroll",
                {
                    "scroll_x": plan.scroll_x,
                    "scroll_y": plan.scroll_y,
                    "x": screen_target[0],
                    "y": screen_target[1],
                },
            )
        elif action_type == "drag":
            assert screen_target is not None and screen_destination is not None
            x1, y1 = screen_target
            x2, y2 = screen_destination
            path = [
                {"x": round(x1 + (x2 - x1) * i / 8), "y": round(y1 + (y2 - y1) * i / 8)}
                for i in range(9)
            ]
            result = await hands.call_tool(
                "hands_computer_action",
                {"action": {"type": "drag", "button": "left", "path": path}},
            )
        elif action_type == "keypress":
            result = await hands.call_tool("hands_keypress", {"keys": list(plan.keys)})
        elif action_type == "type":
            result = await hands.call_tool("hands_type_text", {"text": plan.text or ""})
        elif action_type == "wait":
            await asyncio.sleep(plan.wait_s)
            result = None
        else:  # guarded by PlannedAction validation
            raise ValueError(f"unsupported plan action: {action_type}")

        if result is not None and result.is_error:
            raise RuntimeError(f"Hands action failed: {result.content}")
        return {
            "action_type": action_type,
            "targeting": target_record,
            "hands_result": None if result is None else _structured(result),
        }

    async def _foreground_is_after_effects(self, hands) -> bool:
        status = _structured(await hands.call_tool("hands_status", {}))
        foreground = status.get("foreground") if isinstance(status.get("foreground"), dict) else {}
        return str(foreground.get("process_name") or "").lower() == "afterfx.exe"

    async def run(self, goal: str) -> LiveControllerResult:
        if not goal.strip():
            raise ValueError("controller goal must not be empty")
        history: list[dict[str, Any]] = []
        final_frame_id: int | None = None
        if not self.qwen.health().get("ok"):
            return LiveControllerResult(
                False, "blocked", goal, (), None, "local semantic model is not ready"
            )

        async with Client(self.eyes_url) as eyes, Client(self.hands_url) as hands:
            armed = await hands.call_tool("hands_arm", {})
            if armed.is_error:
                return LiveControllerResult(False, "blocked", goal, (), None, "Hands could not arm")
            started_here = False
            try:
                started = await eyes.call_tool(
                    "eyes_start_live", {"fps": 30, "buffer_seconds": 0.6}
                )
                if started.is_error:
                    return LiveControllerResult(False, "blocked", goal, (), None, "Eyes could not start")
                started_here = bool(_structured(started).get("started", False))

                for index in range(self.max_steps):
                    frame_meta, image = await self._capture_after_effects(eyes, hands)
                    final_frame_id = int(frame_meta.get("frame_id") or 0) or None
                    plan, planner_observation = choose_next_action(
                        image,
                        goal=goal,
                        history=history,
                        client=self.qwen,
                        safe_mode=self.safe_mode,
                    )
                    if plan.status == "blocked":
                        return LiveControllerResult(
                            False,
                            "blocked",
                            goal,
                            tuple(history),
                            final_frame_id,
                            plan.reason or "planner reported blocked",
                        )
                    if plan.status == "done":
                        final_statement = plan.expected or f"The final visible state required by this goal is satisfied: {goal}"
                        final_ok, final_reason, final_obs = verify_visible_state(
                            image,
                            statement=final_statement,
                            client=self.qwen,
                            source="live_controller_goal_verification",
                        )
                        action_verifications = [
                            bool(step["verified"]) for step in history if "verified" in step
                        ]
                        verified_history = not action_verifications or action_verifications[-1]
                        done_record = {
                            "step": index + 1,
                            "plan": plan.as_dict(),
                            "planner": planner_observation.as_dict(),
                            "final_verification": {
                                "ok": final_ok,
                                "reason": final_reason,
                                "semantic": final_obs.as_dict(),
                            },
                        }
                        history.append(done_record)
                        if final_ok and verified_history:
                            return LiveControllerResult(
                                True, "done", goal, tuple(history), final_frame_id, "goal complete"
                            )
                        continue

                    policy_decision = self.policy.authorize(plan)
                    if not policy_decision.allowed:
                        history.append({
                            "step": index + 1,
                            "frame_id": frame_meta.get("frame_id"),
                            "plan": plan.as_dict(),
                            "planner": planner_observation.as_dict(),
                            "policy": policy_decision.as_dict(),
                            "verified": False,
                            "verification_reason": policy_decision.reason,
                        })
                        return LiveControllerResult(
                            False, "blocked", goal, tuple(history), final_frame_id, policy_decision.reason
                        )

                    try:
                        execution = await self._execute_plan(
                            plan=plan,
                            frame_meta=frame_meta,
                            image=image,
                            eyes=eyes,
                            hands=hands,
                        )
                    except StaleObservationError as exc:
                        history.append({
                            "step": index + 1,
                            "frame_id": frame_meta.get("frame_id"),
                            "plan": plan.as_dict(),
                            "planner": planner_observation.as_dict(),
                            "policy": policy_decision.as_dict(),
                            "stale_before_action": True,
                            "verified": False,
                            "verification_reason": str(exc),
                        })
                        continue
                    if plan.action_type != "wait":
                        await asyncio.sleep(0.35)
                    if not await self._foreground_is_after_effects(hands):
                        return LiveControllerResult(
                            False,
                            "blocked",
                            goal,
                            tuple(history),
                            final_frame_id,
                            "After Effects lost foreground after the action",
                        )

                    post_result = await eyes.call_tool(
                        "eyes_latest_frame", {"max_width": 1280, "jpeg_quality": 92}
                    )
                    if post_result.is_error:
                        raise RuntimeError(f"post-action Eyes capture failed: {post_result.content}")
                    post_meta, post_image = _frame_parts(post_result)
                    final_frame_id = int(post_meta.get("frame_id") or 0) or None
                    verified = True
                    verify_reason = "no explicit visible expectation supplied"
                    verify_observation = None
                    if plan.expected:
                        verified, verify_reason, verify_observation = verify_visible_state(
                            post_image,
                            statement=plan.expected,
                            client=self.qwen,
                            source="live_controller_action_verification",
                        )
                    history.append(
                        {
                            "step": index + 1,
                            "frame_id": frame_meta.get("frame_id"),
                            "plan": plan.as_dict(),
                            "planner": planner_observation.as_dict(),
                            "policy": policy_decision.as_dict(),
                            "execution": execution,
                            "post_frame_id": post_meta.get("frame_id"),
                            "verified": verified,
                            "verification_reason": verify_reason,
                            "verification": None
                            if verify_observation is None
                            else verify_observation.as_dict(),
                        }
                    )

                return LiveControllerResult(
                    False,
                    "max_steps",
                    goal,
                    tuple(history),
                    final_frame_id,
                    f"goal did not complete within {self.max_steps} steps",
                )
            finally:
                if started_here:
                    await eyes.call_tool("eyes_stop_live", {})
                await hands.call_tool("hands_disarm", {})
