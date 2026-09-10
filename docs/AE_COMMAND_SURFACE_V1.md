# EditGPT After Effects Command Surface v1

## Status

The After Effects Command Surface is a **shared EditGPT capability**, not an M4-only feature.

It is available to every milestone and must be considered before a milestone creates new UI automation or a new dedicated editing tool for functionality that After Effects already exposes.

Canonical implementation: `src/editgpt/controller/ae_commands.py`.

## Command-first rule

For any After Effects operation, use the strongest existing AE-native route in this order:

1. registered direct After Effects shortcut/command;
2. Quick Apply when it can expose the required effect, animation preset, or menu command;
3. stable After Effects scripting API / `app.executeCommand(id)` transport when available and proven;
4. semantic Eyes + Hands navigation;
5. new custom control tooling only when AE does not already expose a reliable route.

This rule applies to M1, M2, M3, M4, and every later M# phase.

The purpose is not to turn EditGPT into a macro engine. Commands handle deterministic access and operations; Eyes still supplies context and evidence, and higher-level milestones still decide *what* should be done.

## Milestone integration

### M1 — Eyes / perception

Eyes remains read-only. Registered UI commands can place AE into deterministic inspectable states—open a panel, reveal a property, change a viewer zoom, move one frame, or expose the Graph Editor—so perception tests do not waste time finding controls manually. Eyes verifies the result.

### M2 — Hands / execution

Hands is the physical transport for shortcut recipes. A registered command compiles to known Hands steps instead of making the controller rediscover mouse coordinates. The foreground allowlist and Windows input boundary remain unchanged.

### M3 — closed-loop Controller

The planner prefers registered commands before pointer navigation. Because the catalog is now large, `command_keys_for_goal()` supplies a compact goal-relevant subset plus core fallback commands rather than dumping the whole registry into every warm-loop prompt.

This keeps command coverage broad without sacrificing the action-to-action latency target.

### M4 — scoped project mutation

Commands that modify project content declare their semantic mutation kinds. They pass through the same `EditingTaskContract` authorization, pre-mutation Eyes evidence, post-action visual verification, and transaction-owned rollback path as pointer/typing mutations.

A shortcut is never allowed to bypass M4 merely because Adobe implements it natively.

### M5 and later

At the start of every future milestone, perform an **AE-native capability audit** for the functions that phase needs. Add or upgrade command recipes before designing new control primitives. New milestones inherit the same registry automatically.

If a later phase adds a JSX/UXP/in-process scripting bridge, that bridge should be another command transport behind the same stable command keys rather than a parallel unrestricted edit API.

## Registered command contract

Each `AECommandRecipe` declares:

- stable command key;
- human-readable purpose;
- domain (`panel`, `tool`, `composition`, `time`, `preview`, `view`, `footage`, `effect`, `layer`, `property`, `mask`, `keyframe`, `text`, `3d`, etc.);
- transport (`shortcut` or shortcut sequence today);
- deterministic Hands steps;
- safety impact (`reversible_ui`, `project_mutation`, or later explicitly gated categories);
- mutation kinds used by the editing-task contract;
- whether a selected/active semantic target is required;
- source provenance.

The model may emit `action="ae_command"` only with a key that exists in the registry. Invented command keys fail parsing before Hands receives an action.

Double-letter AE shortcuts such as `MM`, `UU`, `RR`, and `EE` are represented as explicit sequential Hands keypresses rather than chords.

## Current breadth

The registry now contains more than 140 AE-native commands spanning:

- panels, viewers, and focus switching;
- tool activation;
- composition/work-area operations;
- time navigation and preview;
- viewer and Timeline zoom/display;
- footage access;
- effects and animation presets;
- layer creation, selection, timing, precomposition, and fitting;
- property reveal/dialog commands;
- masks;
- keyframes and Graph Editor operations;
- text-layer creation;
- 3D views, cameras, lights, and gizmos.

Examples include `panel.effects_presets.toggle`, `tool.roto_brush`, `composition.settings.open`, `time.frame.forward`, `preview.toggle`, `layer.split`, `layer.reverse_time`, `layer.time_remap.enable`, `layer.fit.comp`, `property.scale.reveal`, `mask.new`, `keyframe.ease`, and `layer3d.new_camera`.

## Goal-relevant command selection

A very large registry should not become a very large planner prompt. `command_keys_for_goal(goal)` ranks commands against the task goal and returns a bounded relevant subset while retaining a compact baseline of common commands such as Quick Apply, Selection, panel access, transform-property reveals, frame navigation, and preview.

This means command coverage can continue to grow without linearly increasing warm-loop inference input.

## Quick Apply

Adobe documents Quick Apply as a single search surface for effects, animation presets, and top-level menu commands. EditGPT registers `quick_apply.open` (`Ctrl+Enter` on Windows) as the universal entry point.

Opening Quick Apply itself is reversible UI. Search/result confirmation is still handled conservatively by the normal controller policy until a parameterized Quick Apply recipe has deterministic result-type preconditions. We do **not** assume that pressing Enter on an arbitrary Quick Apply result is safe merely because the search dialog is open.

Official source: https://helpx.adobe.com/after-effects/desktop/animate-in-after-effects/animation-keyframes/quick-apply.html

## Direct scripting / command IDs

After Effects scripting exposes `app.executeCommand(id)` for menu commands and `app.findMenuCommandId(command)` for discovering IDs. This can eventually eliminate even more UI travel.

Command IDs are not treated as globally stable magic numbers without version/platform proof. The registry is intentionally transport-neutral so a proven shortcut recipe can later be upgraded to a scripting/command-ID recipe without changing planner semantics, safety classification, or milestone contracts.

Reference: https://ae-scripting.docsforadobe.dev/general/application/

## Source authority

The expanded Windows shortcut registry was checked against Adobe's current keyboard-shortcut reference on 2026-09-10. Adobe lists the reference as last updated 2026-05-05.

Official source: https://helpx.adobe.com/after-effects/desktop/get-started/keyboard-shortcuts/keyboard-shortcuts-reference.html

When Adobe changes a shortcut or introduces a better native path, update the registry recipe rather than teaching each milestone a separate workaround.

## Architecture decision

No new repository or MCP is required for this command layer.

- Eyes remains read-only evidence.
- Hands remains the guarded physical input boundary.
- Controller owns command selection.
- Editing-task policy owns mutation authorization and rollback.
- Future scripting transports stay behind the same registry.

This is deliberately one shared capability plane across the complete EditGPT roadmap.
