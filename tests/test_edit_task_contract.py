from __future__ import annotations

import numpy as np

from editgpt.controller.edit_task import (
    EditingTaskContract,
    classify_mutation_kinds,
    verify_rollback,
    visual_change_fraction,
)
from editgpt.controller.live_loop import LiveController
from editgpt.controller.planner import PlannedAction


def _plan(action: str, target: str | None, expected: str, **kwargs) -> PlannedAction:
    return PlannedAction(
        status="act",
        action_type=action,
        target=target,
        expected=expected,
        confidence=0.95,
        reason="test plan",
        **kwargs,
    )


def test_contract_allows_only_named_mutation_kind_and_target() -> None:
    contract = EditingTaskContract(
        task_id="m4-transform",
        goal="Increase the selected hero layer scale slightly.",
        allowed_mutations=("transform",),
        target_terms=("hero layer",),
        max_mutations=2,
    )
    allowed = _plan(
        "drag",
        "Scale value for the selected hero layer",
        "hero layer scale is visibly larger",
        destination="slightly larger scale value",
    )
    decision = contract.authorize(allowed, committed_mutations=0)
    assert decision.allowed is True
    assert decision.mutation_kinds == ("transform",)

    wrong_kind = _plan("type", None, "hero layer text content reads HELLO", text="HELLO")
    blocked = contract.authorize(wrong_kind, committed_mutations=0)
    assert blocked.allowed is False
    assert blocked.mutation_kinds == ("text",)


def test_contract_blocks_wrong_target_and_exhausted_budget() -> None:
    contract = EditingTaskContract(
        task_id="m4-opacity",
        goal="Adjust hero layer opacity.",
        allowed_mutations=("transform",),
        target_terms=("hero layer",),
        max_mutations=1,
    )
    wrong_target = _plan(
        "drag",
        "Scale value for background layer",
        "background layer scale is larger",
        destination="larger scale value",
    )
    assert contract.authorize(wrong_target, committed_mutations=0).allowed is False

    in_scope = _plan(
        "drag",
        "Opacity value for hero layer",
        "hero layer opacity is 80 percent",
        destination="80 percent opacity",
    )
    exhausted = contract.authorize(in_scope, committed_mutations=1)
    assert exhausted.allowed is False
    assert "budget" in exhausted.reason


def test_mixed_mutation_requires_every_detected_kind() -> None:
    plan = _plan(
        "click",
        "Position keyframe control for hero layer",
        "a position keyframe is added for hero layer",
    )
    assert classify_mutation_kinds(plan) == ("transform", "keyframe")
    transform_only = EditingTaskContract(
        task_id="transform-only",
        goal="Change hero position.",
        allowed_mutations=("transform",),
        target_terms=("hero layer",),
    )
    assert transform_only.authorize(plan, committed_mutations=0).allowed is False


def test_rollback_verification_uses_deterministic_visual_delta() -> None:
    before = np.zeros((100, 100, 3), dtype=np.uint8)
    restored = before.copy()
    changed = before.copy()
    changed[0:50, 0:50] = 255

    assert visual_change_fraction(before, restored) == 0.0
    assert verify_rollback(before, restored, max_changed_fraction=0.01).ok is True
    failed = verify_rollback(before, changed, max_changed_fraction=0.08)
    assert failed.ok is False
    assert failed.changed_fraction == 0.25


def test_safe_mode_false_alone_no_longer_grants_project_mutation() -> None:
    controller = LiveController(safe_mode=False)
    assert controller.policy.allow_project_mutation is False
    assert controller.editing_task is None


def test_explicit_contract_enables_only_transactional_editing_path() -> None:
    contract = EditingTaskContract(
        task_id="m4-explicit",
        goal="Adjust hero layer scale.",
        allowed_mutations=("transform",),
        target_terms=("hero layer",),
    )
    controller = LiveController(editing_task=contract)
    assert controller.safe_mode is False
    assert controller.policy.allow_project_mutation is True
    assert controller.editing_task is contract
