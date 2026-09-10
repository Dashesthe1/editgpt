# EditGPT Editing Task Contract v1

## Purpose

M4 is the first controller boundary that can intentionally change After Effects project content. It does not grant the planner general edit permission. Every project mutation must be covered by a caller-owned `EditingTaskContract` before Hands executes it.

This remains in the existing EditGPT Controller layer. Eyes stays read-only and Hands stays the guarded write-capable MCP; M4 does not need another repository or MCP.

## Authority model

An editing contract binds all mutation authority to one exact controller goal and declares:

- a stable `task_id`;
- the allowed mutation kinds;
- optional target terms that must be named by the planned mutation;
- the maximum number of committed mutations;
- the rollback key chord (currently `Ctrl+Z` by default);
- the maximum visual difference tolerated after rollback verification.

Supported non-destructive mutation kinds are currently:

- `transform`
- `keyframe`
- `effect`
- `mask`
- `layer_timing`
- `text`
- `shape`
- `composition`
- `footage`
- `layer_structure`
- `generic` (must be explicitly authorized)

A plan that semantically spans multiple mutation kinds must have every detected kind authorized. Destructive actions remain outside M4 even if an Undo path might exist.

## Two independent gates

The model receives the task scope in its planning prompt so it has the information needed to choose a valid action. That prompt is guidance, not authority.

Immediately before execution, deterministic code independently checks:

1. the existing `TaskPolicy` impact class;
2. the M4 editing-task mutation kind;
3. the target-term scope;
4. the remaining committed-mutation budget.

If any gate rejects the action, Hands does not receive it.

Passing `safe_mode=False` by itself no longer enables project mutations in `LiveController`. Without an `EditingTaskContract`, the default policy remains UI-only.

## Transaction lifecycle

For an authorized project mutation the controller records a fresh pre-mutation Eyes frame, executes one action through Hands, captures fresh post-action evidence, and verifies the planner's concrete visible expected state.

If verification passes, the mutation is marked `committed` and consumes one unit of the task's mutation budget.

If verification fails, if post-mutation evidence cannot be captured, or if After Effects loses foreground immediately after the mutation, the controller invokes the predefined rollback chord directly through Hands. The rollback is not model-planned. Eyes then captures another frame and deterministic pixel-delta verification compares it with the pre-mutation evidence.

The controller stops after any rollback attempt. It never keeps editing from an uncertain transaction state.

If the Hands action itself reports an execution failure, the controller does not blindly issue Undo because it cannot know whether Windows/After Effects partially applied the action. It stops with project state marked unknown instead of risking undoing a prior unrelated user edit.

## Rollback verification

`verify_rollback()` computes the fraction of model-visible pixels whose mean channel difference crosses a fixed threshold. A rollback is verified only when that changed fraction is at or below the task contract's `rollback_max_changed_fraction`.

The first default tolerance is `0.08`. This is intentionally a coarse whole-frame safety gate; later M4 work can add region-aware/project-state evidence where a specific After Effects edit exposes a stronger deterministic readback.

## Controller result evidence

M4 history entries add:

- `scope` — the independent task-contract authorization decision;
- `transaction.state` — `committed`, `rolled_back`, or `rollback_failed`;
- rollback Hands evidence;
- rollback frame IDs;
- deterministic rollback changed-fraction evidence;
- the running committed-mutation count.

A failed mutation cannot be reported as successful merely because the planner expected it to work.

## Example contract

```python
EditingTaskContract(
    task_id="hero-scale-pass",
    goal="Increase the selected hero layer scale slightly.",
    allowed_mutations=("transform",),
    target_terms=("hero layer",),
    max_mutations=1,
)
```

The controller must be run with the exact same goal string bound into the contract. A mismatched goal is rejected before semantic planning begins.

## M4 proof gate

The software gate is:

1. unscoped controller runs cannot authorize project mutation;
2. allowed mutation kinds/targets pass;
3. out-of-scope kinds/targets fail closed;
4. mutation budgets are enforced;
5. rollback image verification is deterministic;
6. the Windows test suite passes.

The remaining live workstation gate is to perform a bounded real After Effects project mutation under a contract, prove a verified commit, deliberately exercise a failed verification path, prove `Ctrl+Z` restoration from fresh Eyes evidence, and leave the existing After Effects process running.
