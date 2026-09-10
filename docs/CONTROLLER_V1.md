# EditGPT Controller v1

## Purpose

Controller v1 closes the loop between Eyes, local semantic reasoning, and Hands. It accepts a UI goal, observes the current After Effects state, chooses one constrained next action, executes it, verifies the visible result, and repeats until the goal is complete or the run fails closed.

This controller lives in the existing EditGPT repository. It does **not** require a new MCP: Eyes and Hands remain the correct read/write security boundaries.

## Loop

```text
goal
  |
  v
focus AE -> Eyes frame -> Qwen next-action plan
                           |
                           v
                     fresh AE frame
                           |
                           v
                    Qwen target grounding
                           |
                           v
                    freshness + geometry guard
                           |
                           v
                        Hands action
                           |
                           v
                       Eyes frame
                           |
                           v
                    visible-state verification
                           |
                   continue / done / blocked
```

## Safety contract

Controller v1 deliberately separates **planning** from **grounding**. Qwen plans with semantic target descriptions and is never allowed to provide direct screen coordinates. A second grounding pass locates the requested visible target, then the coordinate bridge converts the Eyes image point to physical screen pixels.

Before a pointer action:

- After Effects is re-focused before the grounding frame is captured.
- Hands still re-checks `AfterFX.exe` as the foreground process at execution time.
- Eyes geometry must remain unchanged between grounding and action.
- The grounded target patch is re-observed after semantic inference; significant visual change makes the observation stale and no action is sent.
- Low-confidence plans or targets fail closed.
- A deterministic Task Policy independently authorizes the action impact before Hands execution; model planning cannot self-authorize project mutation.
- Every planned action must state a visible expected result for post-action verification.

The proof/default `safe_mode` adds another layer: destructive target descriptions are rejected, text entry and double-click are disabled, scroll magnitude is bounded, and only reversible navigation keyboard actions are allowed.

## Current action vocabulary

The generalized planner can choose:

- click
- double-click
- move
- scroll
- keypress
- type
- wait
- drag

Drag is grounded as two independent semantic targets (source and destination) from the same Eyes frame, converted through the physical-pixel coordinate bridge, and executed as a smooth Hands path. In safe mode, drag is limited to reversible UI-state targets such as the playhead/current-time indicator, scrollbars, and panel dividers.

## Live proof

`scripts/prove_controller.py` uses a reversible ordered goal: open the File menu, then switch to Edit, and finish with the Edit dropdown visibly open. The proof cleans up with Escape afterward.

The workstation proof demonstrated genuine feedback behavior rather than a fixed macro:

1. Qwen planned the File-menu click.
2. semantic grounding located File and Hands clicked it.
3. Eyes/Qwen verified the File dropdown opened.
4. Qwen planned the next Edit-menu click from the new visual state and prior history.
5. when an Edit click did not produce the expected visible dropdown state, verification reported failure instead of claiming success.
6. the next iteration re-observed and retried the visible Edit target.
7. Eyes/Qwen verified the Edit dropdown was open.
8. Qwen returned `done`, followed by a separate final visible-state verification.
9. the proof cleanup pressed Escape and Hands disarmed.

This is the first EditGPT proof where the model independently chose multiple sequential UI actions and used visual feedback to recover from an action whose expected result did not appear.

Run it with:

```powershell
.\editgpt.ps1 -Action proof-controller
```

## Reversible drag proof

The controller has independently planned a drag from the timeline start to the 02s ruler mark, grounded the live playhead and destination separately, executed the path through Hands, and verified the playhead at 02s from a fresh Eyes frame. A dedicated `proof-drag` also restores the playhead after validation.

See `docs/TASK_POLICY_V1.md` for the action-impact authorization contract.

## M4: structured transactional editing

M4 extends the same Controller rather than creating another control plane. A caller can attach an `EditingTaskContract` that binds mutation authority to one exact goal, explicit mutation kinds, optional target terms, and a finite mutation budget.

Without that contract, `LiveController` remains UI-only even if `safe_mode=False` is passed. With the contract, the planner may propose non-destructive editing actions, but deterministic Task Policy and task-scope checks must both pass before Hands sees the action.

For each authorized project mutation, the controller captures pre-mutation visual evidence. The mutation is committed only if fresh post-action Eyes evidence satisfies its visible expected state. Failed verification, failed post-action capture, or foreground loss after a mutation triggers the predefined `Ctrl+Z` rollback path and deterministic visual comparison with the pre-mutation frame. The controller stops after rollback instead of continuing from uncertain project state.

See `docs/EDITING_TASK_V1.md` for the full M4 contract.

## Next M4 proof

The code/contract gate is followed by a real After Effects proof: execute one bounded project mutation under an explicit contract, verify a successful commit, deliberately exercise the failed-verification rollback path, verify visual restoration, and reuse the existing After Effects process throughout.
