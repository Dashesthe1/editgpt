# EditGPT Task Policy v1

## Purpose

Task Policy v1 is the safety boundary between Controller planning and Hands execution. It gives EditGPT an explicit, deterministic answer to a question the vision model must not decide by itself: whether the next requested action is allowed to change only UI state, mutate project state, or perform a destructive operation.

This remains inside the existing Controller layer. No new repository or MCP is required.

## Impact classes

Each planned action is classified before execution as one of:

- `reversible_ui` — navigation/state changes such as menus, scrolling, pointer motion, playhead motion, and panel layout drags.
- `project_mutation` — actions that can change layers, keyframes, effects, masks, transforms, text, footage, or composition content.
- `destructive` — delete/remove/purge/overwrite/replace-footage/close-project/quit/exit style operations.
- `ambiguous` — actions whose impact cannot be classified safely from the available contract.

Ambiguous actions fail closed by default.

## Policies

`TaskPolicy.ui_proof()` permits only reversible UI actions. This is the default for Controller proof runs.

`TaskPolicy.editing()` permits reversible UI actions and project mutation, but still blocks destructive operations unless `allow_destructive=True` is explicitly selected by a higher-level task contract.

## Controller integration

Before every `act` plan, `LiveController` now records a `PolicyDecision` and refuses execution when the decision is not allowed. The policy decision is included in controller history alongside the plan, grounding evidence, Hands result, and visual verification.

This does not replace the existing Hands process allowlist, foreground checks, geometry guards, freshness checks, or semantic verification. It is an additional authorization layer.

Safe-mode keyboard navigation now permits Escape, directional arrows, and Home. This is enough for reversible menu/timeline navigation without opening the full shortcut surface to proof runs. The Hands backend separately supports common OEM punctuation keys needed by later After Effects editing shortcuts.

## Live regression

After adding the policy gate, the real After Effects File -> Edit controller proof was rerun. The policy classified both menu clicks as `reversible_ui` and allowed them. The visual loop still rejected failed intermediate clicks, retried from fresh Eyes evidence, opened Edit, and completed only after a separate final visible-state verification passed.

## Next gate

Before EditGPT intentionally changes project content, add structured editing-task state with explicit mutation scope and a rollback/undo verification contract. Project-mutation mode should never be enabled merely because the planner asks for it.
