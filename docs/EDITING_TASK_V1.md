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

## AE Command Surface integration — M4

M4 uses the same cross-milestone After Effects Command Surface as M1-M3. A native AE command is preferred over reproducing the same operation through a long mouse-navigation sequence, but native execution never grants extra authority.

Every registered command declares its impact and, for project mutations, the exact semantic mutation kinds it can create. Examples:

- `property.scale.reveal` — reversible UI; no mutation budget consumed;
- `mask.new` — `project_mutation`, kind `mask`;
- `layer.split` — `project_mutation`, kinds `layer_timing` + `layer_structure`;
- `layer.time_remap.enable` — `project_mutation`, kinds `layer_timing` + `keyframe`;
- `layer.fit.comp` — `project_mutation`, kind `transform`;
- `layer.precompose` — `project_mutation`, kinds `composition` + `layer_structure`.

A command spanning multiple mutation kinds requires the task contract to authorize **all** of them. Merely being registered or implemented by Adobe does not let it bypass policy, target scope, mutation budget, Eyes evidence, or rollback verification.

The M4 command rule is therefore:

1. prefer a registered AE-native operation when it performs the requested edit reliably;
2. authorize it using registry-declared semantics rather than trying to infer mutation type from the physical key chord;
3. capture fresh pre-mutation Eyes evidence;
4. execute through guarded Hands;
5. verify the visible result with fresh Eyes evidence;
6. roll back through the transaction-owned Undo path if verification fails.

See `docs/AE_COMMAND_SURFACE_V1.md` for the shared M1+ architecture.

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

For registered AE commands, controller execution evidence also records the semantic command recipe and its deterministic Hands steps. A failed mutation cannot be reported as successful merely because the planner expected it to work.

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

## M4 live proof harness

`scripts/prove_m4_transaction.py` is the dedicated real-After-Effects M4 gate. It uses the registered native `layer.new.null` command because a new Null layer is visually obvious, bounded to `layer_structure`, and cleanly undoable.

The harness intentionally runs the rollback proof **before** the commit proof:

1. focus the already-running After Effects process, press Escape to settle preview/modal UI, and capture the initial Eyes baseline;
2. semantically confirm that an active composition Timeline is visible before any mutation;
3. execute one authorized `layer.new.null` mutation with an intentionally impossible visual expectation containing the unique `M4_ROLLBACK_SENTINEL_9F3A` title;
4. require the normal M4 action verifier to reject that expectation and require the controller-owned `Ctrl+Z` path to report `transaction.state=rolled_back`;
5. independently capture fresh Eyes evidence and compare it with the initial baseline;
6. only after rollback is proven, execute a second bounded `layer.new.null` mutation with a truthful visible-state expectation and require `transaction.state=committed` plus final goal verification;
7. capture the committed state and require a non-zero viewer-visible change from the restored baseline;
8. issue one cleanup Undo for that intentionally committed proof mutation;
9. capture final Eyes evidence, verify that it matches the initial baseline within rollback tolerance, and require the foreground `AfterFX.exe` process ID to be unchanged from start to finish.

The proof never starts, stops, closes, or restarts After Effects. If rollback cannot be proven, it stops before running the commit case. If a committed proof mutation cannot be cleaned up safely, it reports failure rather than issuing additional blind Undo operations.

The preferred live-gate entrypoint is now the normal EditGPT PowerShell surface:

```powershell
.\editgpt.ps1 -Action proof-m4
```

`proof-m4` performs revision bootstrap when needed, starts/retains the managed Eyes, Hands, and local semantic services, waits until the local semantic verifier is ready, and then invokes `scripts/prove_m4_transaction.py`. It does not manage the After Effects process. `-NoSemantic` is rejected for this proof because real visual verification is part of the gate.

For low-level diagnostic use, the harness can still be invoked directly from an already prepared environment:

```powershell
.\.venv\Scripts\python.exe .\scripts\prove_m4_transaction.py
```

Successful evidence is written to `artifacts/m4-live-proof/`:

- `00_baseline.jpg`
- `01_after_transaction_rollback.jpg`
- `02_committed_null.jpg`
- `03_final_cleanup.jpg`
- `proof.json`

`proof.json` is the authoritative machine-readable result. M4 is not considered live-proven unless all checks are true, including verified rollback, verified commit, visible commit change, baseline restoration after cleanup, and reuse of the same After Effects process.

## M4 proof gate

The software gate is:

1. unscoped controller runs cannot authorize project mutation;
2. allowed mutation kinds/targets pass;
3. out-of-scope kinds/targets fail closed;
4. mutation budgets are enforced;
5. registered command mutations obey the same scope contract as pointer/typing mutations;
6. rollback image verification is deterministic;
7. the Windows test suite passes.

The remaining live workstation gate is to run `.\editgpt.ps1 -Action proof-m4` against the existing After Effects process and obtain `ok: true` in `artifacts/m4-live-proof/proof.json`. That single proof must demonstrate a bounded real AE mutation, a verified commit, a deliberately failed visual verification, verified controller-owned `Ctrl+Z` restoration, proof cleanup back to the initial visible state, and reuse of the same After Effects process.