from __future__ import annotations

import pytest

from editgpt.controller.planner import PlannedAction


def test_planner_parses_safe_click() -> None:
    plan = PlannedAction.from_json_text(
        '{"status":"act","action":"click","target":"File menu label",'
        '"keys":[],"text":null,"scroll_x":0,"scroll_y":0,"wait_s":0.2,'
        '"expected":"File dropdown visible","confidence":0.94,"reason":"visible"}'
    )
    assert plan.status == "act"
    assert plan.action_type == "click"
    assert plan.target == "File menu label"
    assert plan.confidence == pytest.approx(0.94)


def test_planner_parses_done_without_action() -> None:
    plan = PlannedAction.from_json_text(
        '{"status":"done","action":null,"target":null,"expected":"",'
        '"confidence":0.9,"reason":"goal visibly complete"}'
    )
    assert plan.status == "done"
    assert plan.action_type is None


def test_safe_mode_rejects_destructive_target() -> None:
    with pytest.raises(PermissionError, match="rejected target"):
        PlannedAction.from_json_text(
            '{"status":"act","action":"click","target":"Save menu item",'
            '"expected":"save dialog","confidence":0.9,"reason":"requested"}'
        )


def test_safe_mode_only_allows_escape_keypress() -> None:
    with pytest.raises(PermissionError, match="Escape"):
        PlannedAction.from_json_text(
            '{"status":"act","action":"keypress","target":null,"keys":["CTRL","S"],'
            '"expected":"saved","confidence":0.9,"reason":"shortcut"}'
        )


def test_scroll_is_bounded() -> None:
    with pytest.raises(ValueError, match="600"):
        PlannedAction.from_json_text(
            '{"status":"act","action":"scroll","target":"Effects list",'
            '"scroll_y":900,"expected":"list moves","confidence":0.9,"reason":"scroll"}'
        )


def test_action_requires_visible_expected_state() -> None:
    with pytest.raises(ValueError, match="expected state"):
        PlannedAction.from_json_text(
            '{"status":"act","action":"click","target":"File menu label",'
            '"confidence":0.9,"reason":"visible"}'
        )


def test_compact_history_drops_large_semantic_payloads() -> None:
    from editgpt.controller.planner import _compact_history

    compact = _compact_history([
        {
            "step": 1,
            "plan": {"status": "act", "action_type": "click", "target": "File", "expected": "open"},
            "planner": {"text": "very large raw model output"},
            "verified": True,
            "verification_reason": "visible",
        }
    ])
    assert compact == [{
        "step": 1, "status": "act", "action": "click", "target": "File", "expected": "open",
        "verified": True, "verification_reason": "visible", "stale_before_action": False,
        "final_verification_ok": None, "final_verification_reason": None,
    }]
