from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Sequence

import numpy as np

from editgpt.controller.ae_commands import AE_COMMANDS, get_ae_command
from editgpt.eyes.semantic import LocalQwenVLClient, SemanticObservation

_ALLOWED_ACTIONS = {
    "click",
    "double_click",
    "move",
    "scroll",
    "keypress",
    "type",
    "wait",
    "drag",
    "ae_command",
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
    destination: str | None = None
    command: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json_text(cls, text: str, *, safe_mode: bool = True) -> "PlannedAction":
        payload = _parse_json_object(text)
        status = str(payload.get("status", "")).strip().lower()
        if status not in {"act", "done", "blocked"}:
            raise ValueError("planner status must be act, done, or blocked")

        if "confidence" not in payload and status == "act":
            raise ValueError("planner act response requires confidence")
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
        if action in {"click", "double_click", "move", "scroll", "drag"} and not target:
            raise ValueError(f"planned {action} requires a visible target description")
        destination_value = payload.get("destination")
        destination = str(destination_value).strip() if destination_value is not None else None
        if action == "drag" and not destination:
            raise ValueError("planned drag requires a visible destination description")
        if safe_mode and target:
            lowered = target.lower()
            if any(term in lowered for term in _SAFE_TARGET_BLOCKLIST):
                raise PermissionError(f"safe controller mode rejected target: {target!r}")
        if safe_mode and action == "drag":
            allowed_drag_terms = ("playhead", "current-time indicator", "scrollbar", "scroll bar", "panel divider", "panel splitter")
            if not any(term in (target or "").lower() for term in allowed_drag_terms):
                raise PermissionError("safe controller mode only permits reversible UI-state drags")
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
        if safe_mode and action == "keypress" and keys not in {("ESC",), ("ESCAPE",), ("LEFT",), ("RIGHT",), ("UP",), ("DOWN",), ("HOME",)}:
            raise PermissionError("safe controller mode only permits navigation/Escape keypresses")

        typed = payload.get("text")
        typed_text = None if typed is None else str(typed)
        if action == "type" and not typed_text:
            raise ValueError("planned type action requires non-empty text")
        if typed_text is not None and len(typed_text) > 160:
            raise ValueError("planned text exceeds the 160-character safety limit")
        if safe_mode and action == "type":
            raise PermissionError("safe controller mode does not permit text entry")

        command_value = payload.get("command")
        command = str(command_value).strip().lower() if command_value is not None else None
        if action == "ae_command":
            if not command:
                raise ValueError("planned ae_command requires a registered command key")
            try:
                recipe = get_ae_command(command)
            except KeyError as exc:
                raise ValueError(str(exc)) from exc
            if recipe.requires_target and not target:
                raise ValueError(f"After Effects command {command!r} requires a semantic target description")
            if safe_mode and recipe.impact != "reversible_ui":
                raise PermissionError("safe controller mode only permits reversible registered AE commands")
        elif command is not None:
            raise ValueError("command is only valid for action=ae_command")

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
            destination=destination,
            command=command,
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
        record = {
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
        }
        if plan.get("command"):
            record["command"] = plan.get("command")
        compact.append(record)
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
    command_text = ", ".join(sorted(AE_COMMANDS))
    safe_rule = (
        "Safe proof mode is ON. Do not save, close a project, exit, delete, remove, type text, "
        "double-click, or use raw keyboard shortcuts except the permitted navigation keys. Registered ae_command actions are allowed only when their impact is reversible UI."
        if safe_mode
        else "Project-changing actions are allowed only when they are required by the stated goal and pass the external task contract."
    )
    prompt = f"""You are the next-action planner for EditGPT controlling Adobe After Effects.
Use ONLY the visible screenshot plus the supplied action history.
Goal: {goal}
Recent history JSON: {history_text}
{safe_rule}

Prefer a registered After Effects command over mouse navigation when it directly performs the required operation.
Registered AE command keys: {command_text}

Choose exactly one next step. Return ONLY JSON with these keys:
status: "act", "done", or "blocked"
action: one of "click", "double_click", "move", "scroll", "drag", "keypress", "type", "wait", "ae_command", or null
command: registered AE command key for ae_command, otherwise null
target: precise semantic target/context for ae_command or visible UI target for pointer actions, otherwise null
destination: a precise visible UI destination description for drag, otherwise null
keys: array of key names for raw keypress, otherwise []
text: string for type, otherwise null
scroll_x, scroll_y: integer pixel-style wheel deltas, each within -600..600
wait_s: number within 0..1.5 for wait
expected: concise visible state expected immediately after the action
confidence: 0..1
reason: concise reasoning grounded in the visible UI and history

Rules:
- Never output screen coordinates; targeting is grounded separately.
- Registered ae_command keys are deterministic control primitives; never invent a command key.
- Use status=done only when the visible UI AND history show the whole goal is complete.
- The expected field must contain ONLY a concrete visible UI state, never meta claims such as no further action is needed or the goal is complete.
- Follow ordered requirements in the goal; do not skip earlier requested steps just because a later state is visible.
- Use status=blocked if the necessary target/state is not visually clear enough.
- Prefer registered AE commands, then simple reversible UI actions, and use pointer navigation when no reliable command path exists.
- If a top-level menu dropdown is already open and the goal needs an adjacent top-level menu, prefer LEFT/RIGHT keypress navigation over repeatedly clicking another menu label.
"""
    observation = client.observe(
        image,
        prompt=prompt,
        source="live_controller_planner",
        max_tokens=300,
        max_width=image.shape[1],
        jpeg_quality=92,
    )
    try:
        plan = PlannedAction.from_json_text(observation.text, safe_mode=safe_mode)
    except (ValueError, PermissionError, json.JSONDecodeError) as exc:
        repair_prompt = prompt + "\nYour previous response was invalid: " + str(exc) + (
            "\nPrevious response: " + observation.text +
            "\nReturn one corrected JSON object only. For status=act, expected is REQUIRED and must describe an immediately visible post-action state."
        )
        observation = client.observe(
            image, prompt=repair_prompt, source="live_controller_planner_repair",
            max_tokens=340, max_width=image.shape[1], jpeg_quality=92,
        )
        plan = PlannedAction.from_json_text(observation.text, safe_mode=safe_mode)
    if plan.confidence < min_confidence and plan.status == "act":
        raise ValueError(
            f"planner confidence {plan.confidence:.2f} is below required {min_confidence:.2f}; response={observation.text}"
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
            "Do not infer hidden state. Evaluate only the concrete visible-state claim and ignore meta wording about completion. A menu or dropdown being open may itself be the required final state; never require it to close unless the statement explicitly says it must be closed."
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
