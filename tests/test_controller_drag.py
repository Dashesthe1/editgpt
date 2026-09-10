from __future__ import annotations

import json

import pytest

from editgpt.controller.planner import PlannedAction


def test_safe_drag_requires_destination_and_reversible_ui_target() -> None:
    payload = {
        "status": "act",
        "action": "drag",
        "target": "blue current-time indicator playhead",
        "destination": "02s ruler mark",
        "expected": "playhead is at 02s",
        "confidence": 0.95,
        "reason": "reversible timeline navigation",
    }
    plan = PlannedAction.from_json_text(json.dumps(payload), safe_mode=True)
    assert plan.action_type == "drag"
    assert plan.destination == "02s ruler mark"


def test_safe_drag_rejects_project_content_target() -> None:
    payload = {
        "status": "act", "action": "drag", "target": "selected footage layer",
        "destination": "new timeline position", "expected": "layer moved", "confidence": 0.9,
    }
    with pytest.raises(PermissionError, match="reversible UI-state drags"):
        PlannedAction.from_json_text(json.dumps(payload), safe_mode=True)
