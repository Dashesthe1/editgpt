from __future__ import annotations

import pytest

from editgpt.controller.semantic_pointer import SemanticPointerTarget


def test_semantic_pointer_parses_valid_json() -> None:
    target = SemanticPointerTarget.from_json_text(
        '{"target":"File","x":42,"y":18,"confidence":0.92,"reason":"visible menu"}',
        width=1280,
        height=720,
    )
    assert (target.x, target.y) == (42, 18)
    assert target.confidence == pytest.approx(0.92)


def test_semantic_pointer_rejects_out_of_bounds_coordinates() -> None:
    with pytest.raises(ValueError, match="outside"):
        SemanticPointerTarget.from_json_text(
            '{"target":"File","x":1280,"y":18,"confidence":0.9}',
            width=1280,
            height=720,
        )
