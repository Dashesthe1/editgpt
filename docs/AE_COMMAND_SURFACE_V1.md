# EditGPT After Effects Command Surface v1

## Why this exists

EditGPT should not visually hunt through After Effects for controls that AE can already reach deterministically. M4 therefore adds a command-first layer above Hands.

The preferred control order is:

1. registered direct After Effects command;
2. After Effects Quick Apply search;
3. semantic Eyes + mouse/keyboard navigation;
4. manual-style geometric interaction only when the operation genuinely requires it.

This is a speed and reliability optimization, not a replacement for Eyes. Every meaningful state transition is still verified visually, and project-mutating commands still pass through the M4 transaction contract.

## Registered command contract

`src/editgpt/controller/ae_commands.py` is the canonical registry. A command recipe declares:

- stable command key;
- human-readable purpose;
- transport (`shortcut` or shortcut sequence today);
- deterministic Hands steps;
- safety impact (`reversible_ui` or `project_mutation`);
- mutation kinds for M4 scope checks;
- whether a selected/active semantic target is required.

The planner can emit `action="ae_command"` only with a key that exists in the registry. Invented commands fail parsing before Hands receives anything.

## Initial command set

The first registry includes commands for:

- reveal Anchor Point, Position, Scale, Rotation, Opacity, Effects, Mask Path, all Masks, keyframed properties, and modified properties;
- create a new mask (`Ctrl+Shift+N` on Windows);
- enter mask Free Transform;
- open Mask Shape and Mask Feather dialogs;
- open Position, Rotation, and Opacity dialogs;
- open Quick Apply (`Ctrl+Enter` on Windows).

Double-letter After Effects shortcuts such as `MM` and `UU` are represented as explicit sequential Hands keypresses rather than as a chord.

## Quick Apply fallback

After Effects Quick Apply can search and run effects, animation presets, and top-level menu commands. It therefore gives EditGPT a broad deterministic doorway without needing to know the screen position of Effects & Presets, nested menus, or individual menu items.

For operations that are not yet in the registry, the controller can:

1. run `quick_apply.open`;
2. type a search term into the visible Quick Apply field;
3. visually verify the intended result is selected/visible;
4. execute Enter as the actual operation;
5. verify the resulting After Effects state.

Typing into a visible search field is treated as UI navigation, not as a project mutation. If pressing Enter applies an effect or otherwise changes the project, that final action is independently classified and must pass the M4 editing-task scope before execution.

## Mask example

For a selected footage layer, creating a default new mask no longer requires opening Layer > Mask > New Mask with pointer navigation. The planner can request:

```json
{
  "action": "ae_command",
  "command": "mask.new",
  "target": "selected hero footage layer",
  "expected": "a new Mask 1 is visible under the selected hero footage layer"
}
```

`mask.new` is registered as a `project_mutation` with mutation kind `mask`, so it still requires an `EditingTaskContract` that authorizes mask mutation on that target. The controller captures pre-mutation Eyes evidence, sends the exact shortcut through Hands, verifies the new mask visually, and rolls back with the transaction-owned Undo path if verification fails.

## Direct scripting / command IDs

After Effects also exposes `app.executeCommand(id)` for GUI menu commands and `app.findMenuCommandId(command)` for discovering menu-command IDs. Adobe's scripting documentation notes that command IDs can reach some functions not otherwise exposed through the scripting API, while command-name lookup can vary across language packages.

This is a useful later transport for the same registry. We should add it only when EditGPT has a reliable in-process JSX execution path; the registry abstraction is intentionally transport-neutral so shortcut recipes can later be upgraded to command-ID execution without changing planner semantics or M4 authorization.

## Architecture decision

No new MCP is required for Command Surface v1. Hands already provides the guarded keyboard transport, Eyes already verifies the resulting UI, and M4 already owns project-mutation authorization and rollback.

If a future direct JSX bridge is added, it should be implemented as another transport behind the same registered command keys rather than as a parallel unrestricted editing control plane.

## Expansion rule

Whenever EditGPT repeatedly needs to navigate to the same AE function, check in this order:

1. documented direct keyboard shortcut;
2. Quick Apply entry;
3. stable `app.executeCommand` ID / scripting API operation;
4. only then retain a vision-and-pointer recipe.

New commands should be added to the registry with tests before the planner is allowed to use them. This lets the command library grow throughout EditGPT development instead of being milestone-specific throwaway automation.
