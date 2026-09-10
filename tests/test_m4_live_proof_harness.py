from __future__ import annotations

import json

from editgpt.controller.edit_task import classify_mutation_kinds
from editgpt.controller.planner import PlannedAction
from editgpt.controller.policy import classify_action_impact
from scripts.prove_m4_transaction import (
    FORCED_FALSE_EXPECTATION,
    NULL_VISIBLE,
    _act_payload,
    _done_payload,
)


def test_m4_live_proof_uses_registered_null_layer_mutation() -> None:
    plan = PlannedAction.from_json_text(json.dumps(_act_payload(NULL_VISIBLE)), safe_mode=False)
    assert plan.action_type == "ae_command"
    assert plan.command == "layer.new.null"
    assert classify_action_impact(plan) == "project_mutation"
    assert classify_mutation_kinds(plan) == ("layer_structure",)


def test_m4_live_proof_forces_semantic_failure_without_changing_mutation_scope() -> None:
    plan = PlannedAction.from_json_text(json.dumps(_act_payload(FORCED_FALSE_EXPECTATION)), safe_mode=False)
    assert "M4_ROLLBACK_SENTINEL_9F3A" in plan.expected
    assert classify_mutation_kinds(plan) == ("layer_structure",)


def test_m4_commit_proof_finishes_with_visible_null_expectation() -> None:
    done = PlannedAction.from_json_text(json.dumps(_done_payload()), safe_mode=False)
    assert done.status == "done"
    assert done.expected == NULL_VISIBLE
