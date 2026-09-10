# EditGPT Task Policy v1

## Purpose

Task Policy v1 is the safety boundary between Controller planning and Hands execution. It gives EditGPT an explicit, deterministic answer to a question the vision model must not decide by itself: whether the next requested action is allowed to change only UI state, mutate project state, or perform a destructive operation.

This remains inside the existing Controller layer. No new repository or MCP is required.

## Impact classes

Each planned action is classified before execution as one of:

- `reversible_ui` — navigation/state changes such as menus, scrolling, pointer motion, playhead motion, panel layout drags, and registered AE commands whose recipe explicitly declares UI-only impact.
- `project_mutation` — actions that can change layers, keyframes, effects, masks, transforms, text, footage, or composition content.
- `destructive` — delete/remove/purge/overwrite/replace-footage/close-project/quit/exit and other non-transactional side-effect operations such as save/export/render.
- `ambiguous` — actions whose impact cannot be classified safely from the available contract.

Ambiguous actions fail closed by default.

## Registered AE commands

The shared After Effects Command Surface is first-class policy input for M3 and later phases. For `action="ae_command"`, policy does **not** infer safety from the physical shortcut chord. It resolves the registered command recipe and uses that recipe's declared impact.

This matters because the same physical keys can have different meanings in different After Effects contexts. Registration gives the controller a semantic command identity such as `property.scale.reveal`, `layer.split`, or `mask.new`; the physical key sequence remains an implementation detail.

Unknown command keys fail closed before policy execution. Registered project-mutating commands still require M4 task-scope authorization. A future scripting/`app.executeCommand` transport must preserve the same impact metadata and may not bypass policy merely because it avoids mouse/keyboard input.

See `docs/AE_COMMAND_SURFACE_V1.md`.

## Policies

`TaskPolicy.ui_proof()` permits only reversible UI actions. This remains the default whenever no structured editing task is attached.

`TaskPolicy.editing()` can admit non-destructive project-mutation impact, but M4 adds a second required authorization layer: an `EditingTaskContract` must independently approve the mutation kind, target scope, and remaining mutation budget before Hands can execute it.

Passing `safe_mode=False` alone no longer selects the editing policy in `LiveController`; project mutation requires the explicit structured task contract.

## Controller integration

Before every `act` plan, `LiveController` records a `PolicyDecision` and refuses execution when the decision is not allowed. For project mutations, it also records the M4 scope decision. The model cannot self-authorize either layer.

This does not replace the existing Hands process allowlist, foreground checks, geometry guards, freshness checks, or semantic verification. It is an additional authorization layer.

Safe-mode raw keyboard navigation permits Escape, directional arrows, and Home. The Hands backend separately supports the broader key set used by After Effects shortcuts, but those raw keys do not become authorized merely because Hands can physically send them. Command-first operation should use a registered semantic AE command whenever possible instead of asking the planner to improvise a raw shortcut.

## Live regression

After adding the policy gate, the real After Effects File -> Edit controller proof classified both menu clicks as `reversible_ui` and allowed them. The visual loop still rejected failed intermediate clicks, retried from fresh Eyes evidence, opened Edit, and completed only after a separate final visible-state verification passed.

## M4 transactional gate

M4 implements the former next gate: structured editing-task state with explicit mutation scope and rollback/undo verification. An authorized mutation—including an authorized registered AE-native mutation command—is committed only after fresh visual verification. A failed post-mutation verification triggers the contract-owned rollback chord and fresh deterministic rollback evidence, then the controller stops rather than continuing from uncertain state.

See `docs/EDITING_TASK_V1.md` for the complete contract and transaction lifecycle.
