from __future__ import annotations

import asyncio
import json

import pytest

from editgpt.controller.ae_commands import AE_COMMANDS, get_ae_command
from editgpt.controller.edit_task import EditingTaskContract, classify_mutation_kinds
from editgpt.controller.live_loop import LiveController
from editgpt.controller.planner import PlannedAction
from editgpt.controller.policy import TaskPolicy, classify_action_impact


class _Result:
    is_error = False
    structured_content = {"ok": True}


class _FakeHands:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def call_tool(self, name: str, payload: dict):
        self.calls.append((name, payload))
        return _Result()


def _command_plan(command: str, *, target: str | None, expected: str) -> PlannedAction:
    return PlannedAction(
        status="act",
        action_type="ae_command",
        command=command,
        target=target,
        expected=expected,
        confidence=0.95,
        reason="test",
    )


def test_registry_contains_direct_reveal_mask_and_quick_apply_commands() -> None:
    assert "property.position.reveal" in AE_COMMANDS
    assert get_ae_command("property.position.reveal").steps[0].keys == ("P",)
    assert get_ae_command("mask.new").steps[0].keys == ("CTRL", "SHIFT", "N")
    assert get_ae_command("quick_apply.open").steps[0].keys == ("CTRL", "ENTER")


def test_planner_parser_accepts_known_reversible_command_in_safe_mode() -> None:
    payload = json.dumps({
        "status": "act",
        "action": "ae_command",
        "command": "property.scale.reveal",
        "target": "selected hero layer",
        "destination": None,
        "keys": [],
        "text": None,
        "scroll_x": 0,
        "scroll_y": 0,
        "wait_s": 0.25,
        "expected": "Scale property is visible for the selected hero layer",
        "confidence": 0.95,
        "reason": "direct AE command is more reliable than clicking disclosure triangles",
    })
    plan = PlannedAction.from_json_text(payload, safe_mode=True)
    assert plan.command == "property.scale.reveal"
    assert classify_action_impact(plan) == "reversible_ui"
    assert TaskPolicy.ui_proof().authorize(plan).allowed is True


def test_safe_mode_blocks_project_mutating_command() -> None:
    payload = json.dumps({
        "status": "act",
        "action": "ae_command",
        "command": "mask.new",
        "target": "selected hero layer",
        "expected": "a new Mask 1 is visible under the selected hero layer",
        "confidence": 0.95,
        "reason": "use the direct AE mask command",
    })
    with pytest.raises(PermissionError):
        PlannedAction.from_json_text(payload, safe_mode=True)


def test_mask_command_is_scoped_as_mask_mutation() -> None:
    plan = _command_plan(
        "mask.new",
        target="selected hero layer",
        expected="a new Mask 1 is visible under the selected hero layer",
    )
    assert classify_action_impact(plan) == "project_mutation"
    assert classify_mutation_kinds(plan) == ("mask",)
    contract = EditingTaskContract(
        task_id="mask-proof",
        goal="Create a mask on the selected hero layer.",
        allowed_mutations=("mask",),
        target_terms=("hero layer",),
    )
    assert contract.authorize(plan, committed_mutations=0).allowed is True


def test_mask_command_fails_closed_under_wrong_mutation_scope() -> None:
    plan = _command_plan(
        "mask.new",
        target="selected hero layer",
        expected="a new Mask 1 is visible under the selected hero layer",
    )
    contract = EditingTaskContract(
        task_id="transform-only",
        goal="Change hero scale.",
        allowed_mutations=("transform",),
        target_terms=("hero layer",),
    )
    decision = contract.authorize(plan, committed_mutations=0)
    assert decision.allowed is False
    assert decision.mutation_kinds == ("mask",)


def test_registered_command_executor_sends_exact_hands_sequence() -> None:
    plan = _command_plan(
        "property.masks.reveal",
        target="selected hero layer",
        expected="mask property groups are visible for the selected hero layer",
    )
    controller = LiveController()
    hands = _FakeHands()
    result = asyncio.run(controller._execute_registered_command(plan, hands))
    assert hands.calls == [
        ("hands_keypress", {"keys": ["M"]}),
        ("hands_keypress", {"keys": ["M"]}),
    ]
    assert result["command"]["key"] == "property.masks.reveal"


def test_unknown_command_key_is_never_accepted() -> None:
    payload = json.dumps({
        "status": "act",
        "action": "ae_command",
        "command": "mask.magic_auto_everything",
        "target": "hero layer",
        "expected": "a mask is visible",
        "confidence": 0.95,
        "reason": "test invalid command",
    })
    with pytest.raises(ValueError):
        PlannedAction.from_json_text(payload, safe_mode=False)
