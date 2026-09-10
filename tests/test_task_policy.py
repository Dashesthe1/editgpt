from __future__ import annotations

from editgpt.controller.planner import PlannedAction
from editgpt.controller.policy import TaskPolicy, classify_action_impact


def _plan(action: str, target: str | None, expected: str, **kwargs) -> PlannedAction:
    return PlannedAction(
        status="act", action_type=action, target=target, expected=expected,
        confidence=0.9, reason="test", **kwargs,
    )


def test_ui_policy_allows_reversible_navigation_and_playhead_drag() -> None:
    click = _plan("click", "File menu in the top menu bar", "File dropdown is visible")
    drag = _plan(
        "drag", "blue current-time indicator playhead", "playhead is at 02s",
        destination="02s timeline ruler mark",
    )
    assert TaskPolicy.ui_proof().authorize(click).allowed is True
    assert TaskPolicy.ui_proof().authorize(drag).allowed is True
    assert classify_action_impact(drag) == "reversible_ui"


def test_ui_policy_blocks_project_mutation() -> None:
    plan = _plan("drag", "selected footage layer", "layer is moved", destination="later timeline position")
    decision = TaskPolicy.ui_proof().authorize(plan)
    assert decision.allowed is False
    assert decision.impact == "project_mutation"


def test_editing_policy_allows_mutation_but_blocks_destructive_by_default() -> None:
    mutation = _plan("type", None, "text layer content changes", text="hello")
    destructive = _plan("click", "Delete layer menu item", "layer is deleted")
    editing = TaskPolicy.editing()
    assert editing.authorize(mutation).allowed is True
    blocked = editing.authorize(destructive)
    assert blocked.allowed is False
    assert blocked.impact == "destructive"


def test_destructive_policy_requires_explicit_opt_in() -> None:
    destructive = _plan("click", "Delete layer menu item", "layer is deleted")
    decision = TaskPolicy.editing(allow_destructive=True).authorize(destructive)
    assert decision.allowed is True
    assert decision.impact == "destructive"


def test_ui_policy_allows_directional_menu_navigation() -> None:
    plan = _plan("keypress", None, "adjacent menu dropdown is open", keys=("RIGHT",))
    decision = TaskPolicy.ui_proof().authorize(plan)
    assert decision.allowed is True
    assert decision.impact == "reversible_ui"
