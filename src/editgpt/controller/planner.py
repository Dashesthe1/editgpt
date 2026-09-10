from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Sequence

import numpy as np

from editgpt.eyes.semantic import LocalQwenVLClient, SemanticObservation

_ALLOWED_ACTIONS = {
    "click",
    "double_click",
    "move",
    "scroll",
    "keypress",
    "type",
    "wait",
}
_SAFE_TARGET_BLOCKLIST = (
    "save",
    "close project",
    "exit",
    "delete",
    "remove",
    "purge",
)


@dataclass(frozen=True)
class PlannedAction:
    status: str
    action_type: str | None
    target: str | None
    expected: str
    confidence: float
    reason: str
    keys: tuple[str, ...] = ()
    text: str | None = None
    scroll_x: int = 0
    scroll_y: int = 0
    wait_s: float = 0.25

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json_text(cls, text: str, *, safe_mode: bool = True) -> "PlannedAction":
        payload = _parse_json_object(text)
        status = str(payload.get("status", "")).strip().lower()
        if status not in {"act", "done", "blocked"}:
            raise ValueError("planner status must be act, done, or blocked")

        confidence = float(payload.get("confidence", 0.0))
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("planner confidence must be between 0 and 1")
        expected = str(payload.get("expected", "")).strip()
        reason = str(payload.get("reason", "")).strip()
        if status == "act" and not expected:
            raise ValueError("planned action requires a visible expected state for closed-loop verification")
        if status != "act":
            return cls(
                status=status,
                action_type=None,
                target=None,
                expected=expected,
                confidence=confidence,
                reason=reason,
            )

        action = str(payload.get("action", "")).strip().lower()
        if action not in _ALLOWED_ACTIONS:
            raise ValueError(f"unsupported planned action: {action!r}")
        target_value = payload.get("target")
        target = str(target_value).strip() if target_value is not None else None
        if action in {"click", "double_click", "move", "scroll"} and not target:
            raise ValueError(f"planned {action} requires a visible target description")
        if safe_mode and target:
            lowered = target.lower()
            if any(term in lowered for term in _SAFE_TARGET_BLOCKLIST):
                raise PermissionError(f"safe controller mode rejected target: {target!r}")
        if safe_mode and action == "double_click":
            raise PermissionError("safe controller mode does not allow double-click")

        keys_raw = payload.get("keys") or []
        if isinstance(keys_raw, str):
            keys_raw = [keys_raw]
        if not isinstance(keys_raw, list):
            raise ValueError("planner keys must be an array")
        keys = tuple(str(value).upper() for value in keys_raw)
        if len(keys) > 4:
            raise ValueError("planner key chord is too large")
        if action == "keypress" and not keys:
            raise ValueError("planned keypress requires keys")
        if safe_mode and action == "keypress" and keys not in {("ESC",), ("ESCAPE",)}:
            raise PermissionError("safe controller mode only permits Escape keypresses")

        typed = payload.get("text")
        typed_text = None if typed is None else str(typed)
        if action == "type" and not typed_text:
            raise ValueError("planned type action requires non-empty text")
        if typed_text is not None and len(typed_text) > 160:
            raise ValueError("planned text exceeds the 160-character safety limit")
        if safe_mode and action == "type":
            raise PermissionError("safe controller mode does not permit text entry")

        scroll_x = int(payload.get("scroll_x", 0) or 0)
        scroll_y = int(payload.get("scroll_y", 0) or 0)
        if abs(scroll_x) > 600 or abs(scroll_y) > 600:
            raise ValueError("planned scroll exceeds the 600-pixel bound")
        wait_s = float(payload.get("wait_s", 0.25) or 0.25)
        if wait_s < 0.0 or wait_s > 1.5:
            raise ValueError("planned wait must be between 0 and 1.5 seconds")

        return cls(
            status=status,
            action_type=action,
            target=target,
            expected=expected,
            confidence=confidence,
            reason=reason,
            keys=keys,
            text=typed_text,
            scroll_x=scroll_x,
            scroll_y=scroll_y,
            wait_s=wait_s,
        )


def _parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].lstrip()
    payload = json.loads(cleaned)
    if not isinstance(payload, dict):
        raise ValueError("planner response must be a JSON object")
    return payload


def _compact_history(history: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for step in list(history)[-6:]:
        plan = step.get("plan") if isinstance(step.get("plan"), dict) else {}
        final = step.get("final_verification") if isinstance(step.get("final_verification"), dict) else {}
        compact.append({
            "step": step.get("step"),
            "status": plan.get("status"),
            "action": plan.get("action_type"),
            "target": plan.get("target"),
            "expected": plan.get("expected"),
            "verified": step.get("verified"),
            "verification_reason": step.get("verification_reason"),
            "stale_before_action": bool(step.get("stale_before_action", False)),
            "final_verification_ok": final.get("ok"),
            "final_verification_reason": final.get("reason"),
        })
    return compact


def choose_next_action(
    image: np.ndarray,
    *,
    goal: str,
    history: Sequence[dict[str, Any]],
    client: LocalQwenVLClient,
    safe_mode: bool = True,
    min_confidence: float = 0.60,
) -> tuple[PlannedAction, SemanticObservation]:
    if not goal.strip():
        raise ValueError("controller goal must not be empty")
    history_text = json.dumps(_compact_history(history), ensure_ascii=False)
    safe_rule = (
        "Safe proof mode is ON. Do not save, close a project, exit, delete, remove, type text, "
        "double-click, or use any keyboard shortcut except Escape."
        if safe_mode
        else "Project-changing actions are allowed only when they are required by the stated goal."
    )
    prompt = f"""You are the next-action planner for EditGPT controlling Adobe After Effects.
Use ONLY the visible screenshot plus the supplied action history.
Goal: {goal}
Recent history JSON: {history_text}
{safe_rule}

Choose exactly one next step. Return ONLY JSON with these keys:
status: "act", "done", or "blocked"
action: one of "click", "double_click", "move", "scroll", "keypress", "type", "wait", or null
target: a precise visible UI target description for pointer/scroll actions, otherwise null
keys: array of key names for keypress, otherwise []
text: string for type, otherwise null
scroll_x, scroll_y: integer pixel-style wheel deltas, each within -600..600
wait_s: number within 0..1.5 for wait
expected: concise visible state expected immediately after the action
confidence: 0..1
reason: concise reasoning grounded in the visible UI and history

Rules:
- Never output screen coordinates; targeting is grounded separately.
- Use status=done only when the visible UI AND history show the whole goal is complete.
- Follow ordered requirements in the goal; do not skip earlier requested steps just because a later state is visible.
- Use status=blocked if the necessary target/state is not visually clear enough.
- Prefer one simple reversible UI action at a time.
"""
    observation = client.observe(
        image,
        prompt=prompt,
        source="live_controller_planner",
        max_tokens=260,
        max_width=image.shape[1],
        jpeg_quality=92,
    )
    plan = PlannedAction.from_json_text(observation.text, safe_mode=safe_mode)
    if plan.confidence < min_confidence and plan.status != "blocked":
        raise ValueError(
            f"planner confidence {plan.confidence:.2f} is below required {min_confidence:.2f}"
        )
    return plan, observation


def verify_visible_state(
    image: np.ndarray,
    *,
    statement: str,
    client: LocalQwenVLClient,
    source: str = "live_controller_verification",
) -> tuple[bool, str, SemanticObservation]:
    if not statement.strip():
        raise ValueError("verification statement must not be empty")
    observation = client.observe(
        image,
        prompt=(
            "Inspect only the visible Adobe After Effects UI. Decide whether this statement is visibly true: "
            f"{statement}\nReturn ONLY JSON with keys matches (boolean), confidence (0..1), and reason. "
            "Do not infer hidden state."
        ),
        source=source,
        max_tokens=120,
        max_width=image.shape[1],
        jpeg_quality=90,
    )
    payload = _parse_json_object(observation.text)
    matches = bool(payload.get("matches"))
    confidence = float(payload.get("confidence", 1.0))
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("verification confidence must be between 0 and 1")
    reason = str(payload.get("reason", "")).strip()
    return bool(matches and confidence >= 0.60), reason, observation
