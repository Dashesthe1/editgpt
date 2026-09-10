from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Sequence

import cv2
from mcp import Client

from editgpt.controller.edit_task import EditingTaskContract, verify_rollback, visual_change_fraction
from editgpt.controller.live_loop import LiveController, _frame_parts, _structured
from editgpt.controller.planner import verify_visible_state
from editgpt.eyes.semantic import LocalQwenVLClient, SemanticObservation

EYES_URL = "http://127.0.0.1:8765/mcp"
HANDS_URL = "http://127.0.0.1:8766/mcp"
OUTPUT_DIR = Path("artifacts/m4-live-proof")
ROLLBACK_GOAL = (
    "Create one temporary null layer in the active Adobe After Effects composition so M4 can "
    "prove that a failed visual expectation is automatically rolled back."
)
COMMIT_GOAL = (
    "Create one null layer in the active Adobe After Effects composition and leave the resulting "
    "null layer visibly present in the Timeline."
)
NULL_VISIBLE = "A selected null layer is visibly present in the active After Effects Timeline."
FORCED_FALSE_EXPECTATION = (
    "A selected null layer is visibly present in the active After Effects Timeline, and a giant "
    "title reading M4_ROLLBACK_SENTINEL_9F3A is visibly rendered in the Composition viewer."
)


class ScriptedPlanningClient:
    """Use deterministic proof plans while delegating all visual judgments to local Qwen."""

    def __init__(self, delegate: LocalQwenVLClient, planner_payloads: Sequence[dict[str, Any]]) -> None:
        self.delegate = delegate
        self.planner_payloads = tuple(planner_payloads)
        self.index = 0

    def health(self) -> dict[str, Any]:
        return self.delegate.health()

    def observe(
        self,
        image,
        *,
        prompt: str,
        source: str = "live_frame",
        max_tokens: int = 320,
        max_width: int = 1280,
        jpeg_quality: int = 90,
    ) -> SemanticObservation:
        if source.startswith("live_controller_planner"):
            if self.index >= len(self.planner_payloads):
                payload = {
                    "status": "blocked",
                    "expected": "",
                    "confidence": 1.0,
                    "reason": "M4 proof planner exhausted its deterministic action sequence.",
                }
            else:
                payload = self.planner_payloads[self.index]
                self.index += 1
            return SemanticObservation(
                model="editgpt-m4-scripted-planner",
                text=json.dumps(payload),
                latency_s=0.0,
                source=source,
            )
        return self.delegate.observe(
            image,
            prompt=prompt,
            source=source,
            max_tokens=max_tokens,
            max_width=max_width,
            jpeg_quality=jpeg_quality,
        )


def _act_payload(expected: str) -> dict[str, Any]:
    return {
        "status": "act",
        "action": "ae_command",
        "command": "layer.new.null",
        "target": None,
        "destination": None,
        "keys": [],
        "text": None,
        "scroll_x": 0,
        "scroll_y": 0,
        "wait_s": 0.25,
        "expected": expected,
        "confidence": 1.0,
        "reason": "Use the registered native After Effects new-null command for the M4 proof.",
    }


def _done_payload() -> dict[str, Any]:
    return {
        "status": "done",
        "action": None,
        "command": None,
        "target": None,
        "destination": None,
        "keys": [],
        "text": None,
        "scroll_x": 0,
        "scroll_y": 0,
        "wait_s": 0.0,
        "expected": NULL_VISIBLE,
        "confidence": 1.0,
        "reason": "The bounded commit proof has performed its one authorized mutation.",
    }


def _transaction(result, state: str) -> dict[str, Any] | None:
    for step in result.steps:
        transaction = step.get("transaction") if isinstance(step, dict) else None
        if isinstance(transaction, dict) and transaction.get("state") == state:
            return transaction
    return None


def _foreground_pid(status: dict[str, Any]) -> int | None:
    foreground = status.get("foreground") if isinstance(status.get("foreground"), dict) else {}
    value = foreground.get("process_id")
    return int(value) if isinstance(value, int) and value > 0 else None


async def _capture_after_effects(eyes, hands, *, escape_first: bool = False):
    armed = await hands.call_tool("hands_arm", {})
    if armed.is_error:
        raise RuntimeError("Hands could not arm for M4 proof capture")
    try:
        focused = await hands.call_tool("hands_focus_after_effects", {})
        if focused.is_error:
            raise RuntimeError("After Effects could not be focused for M4 proof capture")
        if escape_first:
            escaped = await hands.call_tool("hands_keypress", {"keys": ["ESC"]})
            if escaped.is_error:
                raise RuntimeError("Could not settle After Effects with Escape before M4 proof")
        await asyncio.sleep(0.20)
        status_result = await hands.call_tool("hands_status", {})
        if status_result.is_error:
            raise RuntimeError("Hands status failed during M4 proof capture")
        frame_result = await eyes.call_tool("eyes_latest_frame", {"max_width": 1280, "jpeg_quality": 92})
        if frame_result.is_error:
            raise RuntimeError("Eyes capture failed during M4 proof")
        meta, image = _frame_parts(frame_result)
        return meta, image, _structured(status_result)
    finally:
        await hands.call_tool("hands_disarm", {})


async def _undo_cleanup(hands) -> dict[str, Any]:
    armed = await hands.call_tool("hands_arm", {})
    if armed.is_error:
        return {"ok": False, "reason": "Hands could not arm for proof cleanup"}
    try:
        focused = await hands.call_tool("hands_focus_after_effects", {})
        if focused.is_error:
            return {"ok": False, "reason": "After Effects could not be focused for proof cleanup"}
        undone = await hands.call_tool("hands_keypress", {"keys": ["CTRL", "Z"]})
        if undone.is_error:
            return {"ok": False, "reason": "cleanup Undo failed"}
        await asyncio.sleep(0.45)
        return {"ok": True, "hands_result": _structured(undone)}
    finally:
        await hands.call_tool("hands_disarm", {})


async def prove() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    qwen = LocalQwenVLClient()
    payload: dict[str, Any] = {
        "type": "editgpt_m4_live_transaction_proof",
        "mutation_command": "layer.new.null",
        "rollback_order": "rollback proof first, commit proof second, then cleanup commit",
        "checks": {},
    }

    async with Client(EYES_URL) as eyes, Client(HANDS_URL) as hands:
        started = await eyes.call_tool("eyes_start_live", {"fps": 30, "buffer_seconds": 0.6})
        if started.is_error:
            payload["error"] = "Eyes could not start live capture"
            (OUTPUT_DIR / "proof.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
            print(json.dumps(payload, indent=2))
            return 2
        started_here = bool(_structured(started).get("started", False))
        try:
            baseline_meta, baseline_image, baseline_status = await _capture_after_effects(
                eyes, hands, escape_first=True
            )
            cv2.imwrite(str(OUTPUT_DIR / "00_baseline.jpg"), baseline_image)
            preflight_ok, preflight_reason, preflight_obs = verify_visible_state(
                baseline_image,
                statement="An active After Effects composition Timeline is visibly open and able to receive a new layer.",
                client=qwen,
                source="m4_live_preflight",
            )
            payload["preflight"] = {
                "ok": preflight_ok,
                "reason": preflight_reason,
                "frame_id": baseline_meta.get("frame_id"),
                "semantic": preflight_obs.as_dict(),
                "hands_status": baseline_status,
            }
            if not preflight_ok:
                payload["error"] = "M4 live proof requires a visibly active composition Timeline before mutating."
                (OUTPUT_DIR / "proof.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
                print(json.dumps(payload, indent=2))
                return 2

            rollback_contract = EditingTaskContract(
                task_id="m4-live-rollback-null",
                goal=ROLLBACK_GOAL,
                allowed_mutations=("layer_structure",),
                max_mutations=1,
            )
            rollback_controller = LiveController(
                qwen=ScriptedPlanningClient(qwen, [_act_payload(FORCED_FALSE_EXPECTATION)]),
                editing_task=rollback_contract,
                max_steps=2,
            )
            rollback_result = await rollback_controller.run(ROLLBACK_GOAL)
            rollback_tx = _transaction(rollback_result, "rolled_back")
            rollback_ok = bool(
                rollback_result.status == "rolled_back"
                and rollback_tx
                and isinstance(rollback_tx.get("rollback"), dict)
                and rollback_tx["rollback"].get("ok") is True
            )
            payload["rollback_run"] = rollback_result.as_dict()
            payload["checks"]["forced_verification_failure_rolled_back"] = rollback_ok
            if not rollback_ok:
                payload["error"] = "Forced-verification failure did not produce a verified M4 rollback; stopping before commit proof."
                (OUTPUT_DIR / "proof.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
                print(json.dumps(payload, indent=2))
                return 3

            restored_meta, restored_image, restored_status = await _capture_after_effects(eyes, hands)
            cv2.imwrite(str(OUTPUT_DIR / "01_after_transaction_rollback.jpg"), restored_image)
            rollback_corroboration = verify_rollback(baseline_image, restored_image)
            payload["rollback_corroboration"] = {
                **rollback_corroboration.as_dict(),
                "frame_id": restored_meta.get("frame_id"),
                "hands_status": restored_status,
            }
            payload["checks"]["rollback_matches_initial_baseline"] = rollback_corroboration.ok
            if not rollback_corroboration.ok:
                payload["error"] = "Fresh post-rollback evidence did not match the initial baseline closely enough."
                (OUTPUT_DIR / "proof.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
                print(json.dumps(payload, indent=2))
                return 4

            commit_contract = EditingTaskContract(
                task_id="m4-live-commit-null",
                goal=COMMIT_GOAL,
                allowed_mutations=("layer_structure",),
                max_mutations=1,
            )
            commit_controller = LiveController(
                qwen=ScriptedPlanningClient(qwen, [_act_payload(NULL_VISIBLE), _done_payload()]),
                editing_task=commit_contract,
                max_steps=3,
            )
            commit_result = await commit_controller.run(COMMIT_GOAL)
            commit_tx = _transaction(commit_result, "committed")
            commit_ok = bool(commit_result.ok and commit_result.status == "done" and commit_tx)
            payload["commit_run"] = commit_result.as_dict()
            payload["checks"]["bounded_mutation_committed"] = commit_ok
            if not commit_ok:
                payload["error"] = "Bounded M4 mutation did not reach a verified committed state."
                (OUTPUT_DIR / "proof.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
                print(json.dumps(payload, indent=2))
                return 5

            committed_meta, committed_image, committed_status = await _capture_after_effects(eyes, hands)
            cv2.imwrite(str(OUTPUT_DIR / "02_committed_null.jpg"), committed_image)
            committed_change = visual_change_fraction(restored_image, committed_image)
            payload["commit_corroboration"] = {
                "visible_changed_fraction": committed_change,
                "frame_id": committed_meta.get("frame_id"),
                "hands_status": committed_status,
            }
            payload["checks"]["commit_produced_visible_change"] = committed_change >= 0.001

            cleanup = await _undo_cleanup(hands)
            payload["cleanup"] = cleanup
            if not cleanup.get("ok"):
                payload["error"] = "Committed proof mutation succeeded, but cleanup Undo failed."
                (OUTPUT_DIR / "proof.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
                print(json.dumps(payload, indent=2))
                return 6

            final_meta, final_image, final_status = await _capture_after_effects(eyes, hands)
            cv2.imwrite(str(OUTPUT_DIR / "03_final_cleanup.jpg"), final_image)
            cleanup_verification = verify_rollback(baseline_image, final_image)
            baseline_pid = _foreground_pid(baseline_status)
            final_pid = _foreground_pid(final_status)
            same_ae_process = bool(baseline_pid and baseline_pid == final_pid)
            payload["final_cleanup_verification"] = {
                **cleanup_verification.as_dict(),
                "baseline_frame_id": baseline_meta.get("frame_id"),
                "final_frame_id": final_meta.get("frame_id"),
                "baseline_afterfx_pid": baseline_pid,
                "final_afterfx_pid": final_pid,
            }
            payload["checks"]["proof_cleanup_restored_baseline"] = cleanup_verification.ok
            payload["checks"]["same_after_effects_process_reused"] = same_ae_process
            payload["checks"]["commit_produced_visible_change"] = committed_change >= 0.001
            payload["ok"] = all(bool(value) for value in payload["checks"].values())
        finally:
            if started_here:
                await eyes.call_tool("eyes_stop_live", {})

    (OUTPUT_DIR / "proof.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload.get("ok") else 7


def main() -> int:
    return asyncio.run(prove())


if __name__ == "__main__":
    raise SystemExit(main())
