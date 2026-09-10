# EditGPT Hands v1

## Purpose

Hands gives GPT a deterministic, local mouse/keyboard execution layer for Adobe After Effects. It complements Eyes rather than replacing it:

- **Eyes** supplies timestamped visual evidence and high-rate perception.
- **Hands** performs guarded desktop actions.
- A reasoning/controller layer can combine both without coupling itself to one model provider or one UI-driving implementation.

The first backend is native Win32 `SendInput`/window APIs. It has no recurring inference or automation-service cost.

## Security boundary

Hands is intentionally a **separate MCP server** from Eyes because it is write-capable.

Defaults:

- localhost only: `http://127.0.0.1:8766/mcp`;
- starts **disarmed**;
- default process allowlist: `AfterFX.exe` only;
- every mouse/keyboard action re-checks the foreground process;
- focusing a window is also limited to the allowlist;
- a non-loopback bind requires an explicit override and is not considered production-safe without authenticated transport.

Eyes remains on port `8765` and does not gain write permissions.

## MCP surface

- `hands_status`
- `hands_arm`
- `hands_disarm`
- `hands_focus_after_effects`
- `hands_computer_action`
- `hands_move`
- `hands_click`
- `hands_scroll`
- `hands_keypress`
- `hands_type_text`

`hands_computer_action` accepts a compact computer-use-style action object. Supported action types are:

- `click`
- `double_click`
- `move`
- `scroll`
- `keypress` / `key_press`
- `type`
- `drag`
- `wait`

Screenshots stay in Eyes so the write-capable server never needs to own the visual pipeline.

## One-command lifecycle

The normal launcher starts Eyes MCP, Hands MCP, and the semantic service:

```powershell
.\editgpt.ps1
```

Hands status/logging/proof are integrated into the same control plane:

```powershell
.\editgpt.ps1 -Action status
.\editgpt.ps1 -Action logs -Service hands_mcp
.\editgpt.ps1 -Action proof-hands
```

`proof-hands` is intentionally non-destructive. It discovers the Hands MCP tools, arms Hands, focuses After Effects, reads the real cursor position, sends a move to that exact same coordinate, and disarms Hands. `proof-semantic-click` is the next guarded UI proof: Eyes captures AE, local Qwen grounds the File menu, Hands clicks it, Eyes verifies the dropdown opened, Hands presses Esc, and Eyes verifies it closed again.

## Controller compatibility

Hands is designed so a controller can translate model-generated computer actions into the same local execution contract. This lets EditGPT use a capable hosted computer-use model when desired, while preserving a provider-independent local Hands API and the local Eyes stack.

The durable architecture is therefore:

```text
GPT/controller
   |             \
   | observe      \ act
   v               v
Eyes MCP        Hands MCP
(read-only)     (write-capable, armed + allowlisted)
   |               |
 DXcam/...       Win32 SendInput
    \             /
      After Effects
```

## Definition of proven

Hands v1 is not complete merely because the server starts. The real workstation gate is:

1. MCP surface discovery succeeds.
2. Hands reports the correct foreground process and cursor geometry.
3. Disarmed actions are rejected.
4. Non-allowlisted foreground actions are rejected.
5. After Effects can be focused through the guarded focus operation.
6. A no-op cursor move succeeds through the MCP action path.
7. A later deliberate AE interaction proof confirms click, keyboard shortcut, text entry, scroll, and drag behavior against disposable test UI/state.
8. Hands is re-disarmed after proofs.

The first live proof intentionally stops at item 6 so it cannot mutate an editing project while validating the transport and native input path.
