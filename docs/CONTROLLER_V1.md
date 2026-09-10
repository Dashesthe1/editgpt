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
- Every planned action must state a visible expected result for post-action verification.

The proof/default `safe_mode` adds another layer: destructive target descriptions are rejected, text entry and double-click are disabled, scroll magnitude is bounded, and the only keyboard action allowed is Escape.

## Current action vocabulary

The first generalized planner can choose:

- click
- double-click
- move
- scroll
- keypress
- type
- wait

Hands already supports drag. Generalized semantic drag planning will be added after source/destination grounding has its own proof contract rather than allowing an unconstrained model-generated path.

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

## Next milestone

Controller v1 is still a GUI-control foundation, not yet a professional autonomous editor. The next work is to add structured editing-task state, semantic drag source/destination grounding, richer keyboard shortcut coverage, and action policies that distinguish reversible UI navigation from intentional project mutations.
