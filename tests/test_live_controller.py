from __future__ import annotations

import numpy as np

from editgpt.controller.live_loop import _target_patch_change


def test_target_patch_change_is_zero_for_identical_frames() -> None:
    image = np.zeros((100, 120, 3), dtype=np.uint8)
    assert _target_patch_change(image, image.copy(), (20, 20, 40, 40)) == 0.0


def test_target_patch_change_detects_changed_target_region() -> None:
    before = np.zeros((100, 120, 3), dtype=np.uint8)
    after = before.copy()
    after[20:41, 20:41] = 255
    changed = _target_patch_change(before, after, (20, 20, 40, 40))
    assert changed > 0.1
