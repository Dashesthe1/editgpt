from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any


ADOBE_SHORTCUT_REFERENCE = (
    "Adobe After Effects keyboard shortcut reference, verified 2026-09-10 "
    "against Adobe documentation last updated 2026-05-05"
)
ADOBE_QUICK_APPLY_REFERENCE = (
    "Adobe After Effects Quick Apply documentation, verified 2026-09-10 "
    "against Adobe documentation last updated 2026-04-15"
)


@dataclass(frozen=True)
class AECommandStep:
    action: str
    keys: tuple[str, ...] = ()
    text: str | None = None
    wait_s: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AECommandRecipe:
    key: str
    description: str
    transport: str
    impact: str
    steps: tuple[AECommandStep, ...]
    mutation_kinds: tuple[str, ...] = ()
    requires_target: bool = False
    domain: str = "general"
    source: str = ADOBE_SHORTCUT_REFERENCE

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _shortcut(
    key: str,
    description: str,
    keys: tuple[str, ...],
    *,
    impact: str = "reversible_ui",
    mutation_kinds: tuple[str, ...] = (),
    requires_target: bool = False,
    domain: str = "general",
    source: str = ADOBE_SHORTCUT_REFERENCE,
) -> AECommandRecipe:
    return AECommandRecipe(
        key=key,
        description=description,
        transport="shortcut",
        impact=impact,
        mutation_kinds=mutation_kinds,
        requires_target=requires_target,
        domain=domain,
        source=source,
        steps=(AECommandStep("keypress", keys=keys),),
    )


def _sequence(
    key: str,
    description: str,
    keys: tuple[str, ...],
    *,
    impact: str = "reversible_ui",
    mutation_kinds: tuple[str, ...] = (),
    requires_target: bool = False,
    domain: str = "timeline",
) -> AECommandRecipe:
    return AECommandRecipe(
        key=key,
        description=description,
        transport="shortcut_sequence",
        impact=impact,
        mutation_kinds=mutation_kinds,
        requires_target=requires_target,
        domain=domain,
        steps=tuple(AECommandStep("keypress", keys=(value,)) for value in keys),
    )


AE_COMMANDS: dict[str, AECommandRecipe] = {
    # Universal command/search access.
    "quick_apply.open": _shortcut(
        "quick_apply.open", "Open After Effects Quick Apply search", ("CTRL", "ENTER"),
        domain="search", source=ADOBE_QUICK_APPLY_REFERENCE,
    ),
    "keyboard_shortcuts.open": _shortcut(
        "keyboard_shortcuts.open", "Open the Visual Keyboard Shortcut Editor", ("CTRL", "ALT", "APOSTROPHE"),
        domain="preferences",
    ),
    "selection.all": _shortcut(
        "selection.all", "Select all items in the active After Effects context", ("CTRL", "A"), domain="selection"
    ),
    "selection.none": _shortcut(
        "selection.none", "Deselect all items in the active After Effects context", ("CTRL", "SHIFT", "A"), domain="selection"
    ),

    # Panels, viewers, and workspace access.
    "panel.project.toggle": _shortcut("panel.project.toggle", "Open or close Project panel", ("CTRL", "0"), domain="panel"),
    "panel.render_queue.toggle": _shortcut("panel.render_queue.toggle", "Open or close Render Queue panel", ("CTRL", "ALT", "0"), domain="panel"),
    "panel.tools.toggle": _shortcut("panel.tools.toggle", "Open or close Tools panel", ("CTRL", "1"), domain="panel"),
    "panel.info.toggle": _shortcut("panel.info.toggle", "Open or close Info panel", ("CTRL", "2"), domain="panel"),
    "panel.preview.toggle": _shortcut("panel.preview.toggle", "Open or close Preview panel", ("CTRL", "3"), domain="panel"),
    "panel.audio.toggle": _shortcut("panel.audio.toggle", "Open or close Audio panel", ("CTRL", "4"), domain="panel"),
    "panel.effects_presets.toggle": _shortcut("panel.effects_presets.toggle", "Open or close Effects & Presets panel", ("CTRL", "5"), domain="panel"),
    "panel.character.toggle": _shortcut("panel.character.toggle", "Open or close Character panel", ("CTRL", "6"), domain="panel"),
    "panel.paragraph.toggle": _shortcut("panel.paragraph.toggle", "Open or close Paragraph panel", ("CTRL", "7"), domain="panel"),
    "panel.paint.toggle": _shortcut("panel.paint.toggle", "Open or close Paint panel", ("CTRL", "8"), domain="panel"),
    "panel.brushes.toggle": _shortcut("panel.brushes.toggle", "Open or close Brushes panel", ("CTRL", "9"), domain="panel"),
    "panel.effect_controls.open": _shortcut(
        "panel.effect_controls.open", "Open Effect Controls panel for selected layer", ("F3",),
        requires_target=True, domain="panel",
    ),
    "panel.project_flowchart.open": _shortcut(
        "panel.project_flowchart.open", "Open project Flowchart panel", ("CTRL", "F11"), domain="panel"
    ),
    "focus.comp_timeline.toggle": _shortcut(
        "focus.comp_timeline.toggle", "Toggle activation between Composition and Timeline panels", ("BACKSLASH",), domain="panel"
    ),
    "viewer.previous": _shortcut("viewer.previous", "Cycle to previous item in active viewer", ("SHIFT", "COMMA"), domain="panel"),
    "viewer.next": _shortcut("viewer.next", "Cycle to next item in active viewer", ("SHIFT", "PERIOD"), domain="panel"),
    "panel.previous": _shortcut("panel.previous", "Cycle to previous panel in active frame", ("ALT", "SHIFT", "COMMA"), domain="panel"),
    "panel.next": _shortcut("panel.next", "Cycle to next panel in active frame", ("ALT", "SHIFT", "PERIOD"), domain="panel"),

    # Tool activation.
    "tool.selection": _shortcut("tool.selection", "Activate Selection tool", ("V",), domain="tool"),
    "tool.hand": _shortcut("tool.hand", "Activate Hand tool", ("H",), domain="tool"),
    "tool.zoom": _shortcut("tool.zoom", "Activate Zoom tool", ("Z",), domain="tool"),
    "tool.rotation": _shortcut("tool.rotation", "Activate Rotation tool", ("W",), domain="tool"),
    "tool.roto_brush": _shortcut("tool.roto_brush", "Activate Roto Brush or Refine Edge tool", ("ALT", "W"), domain="tool"),
    "tool.camera.cycle": _shortcut("tool.camera.cycle", "Activate and cycle Camera tools", ("C",), domain="tool"),
    "tool.pan_behind": _shortcut("tool.pan_behind", "Activate Pan Behind tool", ("Y",), domain="tool"),
    "tool.mask_shape.cycle": _shortcut("tool.mask_shape.cycle", "Activate and cycle mask and shape tools", ("Q",), domain="tool"),
    "tool.type.cycle": _shortcut("tool.type.cycle", "Activate and cycle Type tools", ("CTRL", "T"), domain="tool"),
    "tool.pen_mask_feather.cycle": _shortcut("tool.pen_mask_feather.cycle", "Activate and cycle Pen and Mask Feather tools", ("G",), domain="tool"),
    "tool.brush_clone_eraser.cycle": _shortcut("tool.brush_clone_eraser.cycle", "Activate and cycle Brush, Clone Stamp, and Eraser tools", ("CTRL", "B"), domain="tool"),
    "tool.puppet.cycle": _shortcut("tool.puppet.cycle", "Activate and cycle Puppet tools", ("CTRL", "P"), domain="tool"),

    # Composition and work-area operations.
    "composition.new": _shortcut(
        "composition.new", "Create a new composition", ("CTRL", "N"), impact="project_mutation",
        mutation_kinds=("composition",), domain="composition",
    ),
    "composition.settings.open": _shortcut(
        "composition.settings.open", "Open Composition Settings for selected composition", ("CTRL", "K"),
        requires_target=True, domain="composition",
    ),
    "work_area.start.set": _shortcut(
        "work_area.start.set", "Set beginning of work area to current time", ("B",), impact="project_mutation",
        mutation_kinds=("composition",), domain="composition",
    ),
    "work_area.end.set": _shortcut(
        "work_area.end.set", "Set end of work area to current time", ("N",), impact="project_mutation",
        mutation_kinds=("composition",), domain="composition",
    ),
    "work_area.fit_selection": _shortcut(
        "work_area.fit_selection", "Set work area to selected layers or composition duration", ("CTRL", "ALT", "B"),
        impact="project_mutation", mutation_kinds=("composition",), domain="composition",
    ),
    "composition.miniflowchart.open": _shortcut(
        "composition.miniflowchart.open", "Open Composition Mini-Flowchart", ("TAB",), domain="composition"
    ),
    "composition.hierarchy.previous": _shortcut(
        "composition.hierarchy.previous", "Activate previous composition in current hierarchy", ("SHIFT", "ESC"), domain="composition"
    ),
    "composition.trim_to_work_area": _shortcut(
        "composition.trim_to_work_area", "Trim composition to work area", ("CTRL", "SHIFT", "X"),
        impact="project_mutation", mutation_kinds=("composition",), domain="composition",
    ),
    "composition.from_selection": _shortcut(
        "composition.from_selection", "Create new composition from selection", ("ALT", "BACKSLASH"),
        impact="project_mutation", mutation_kinds=("composition",), requires_target=True, domain="composition",
    ),

    # Timeline/time navigation and preview.
    "time.goto_dialog": _shortcut("time.goto_dialog", "Open Go To Time dialog", ("ALT", "SHIFT", "J"), domain="time"),
    "time.work_area.begin": _shortcut("time.work_area.begin", "Go to beginning of work area", ("SHIFT", "HOME"), domain="time"),
    "time.work_area.end": _shortcut("time.work_area.end", "Go to end of work area", ("SHIFT", "END"), domain="time"),
    "time.visible_item.previous": _shortcut("time.visible_item.previous", "Go to previous visible time-ruler item", ("J",), domain="time"),
    "time.visible_item.next": _shortcut("time.visible_item.next", "Go to next visible time-ruler item", ("K",), domain="time"),
    "time.begin": _shortcut("time.begin", "Go to beginning of composition, layer, or footage", ("HOME",), domain="time"),
    "time.end": _shortcut("time.end", "Go to end of composition, layer, or footage", ("END",), domain="time"),
    "time.frame.forward": _shortcut("time.frame.forward", "Go forward one frame", ("PAGEDOWN",), domain="time"),
    "time.frames10.forward": _shortcut("time.frames10.forward", "Go forward ten frames", ("SHIFT", "PAGEDOWN"), domain="time"),
    "time.frame.backward": _shortcut("time.frame.backward", "Go backward one frame", ("PAGEUP",), domain="time"),
    "time.frames10.backward": _shortcut("time.frames10.backward", "Go backward ten frames", ("SHIFT", "PAGEUP"), domain="time"),
    "time.layer_in": _shortcut("time.layer_in", "Go to selected layer In point", ("I",), requires_target=True, domain="time"),
    "time.layer_out": _shortcut("time.layer_out", "Go to selected layer Out point", ("O",), requires_target=True, domain="time"),
    "time.inout.previous": _shortcut("time.inout.previous", "Go to previous layer In or Out point", ("CTRL", "ALT", "SHIFT", "LEFT"), domain="time"),
    "time.inout.next": _shortcut("time.inout.next", "Go to next layer In or Out point", ("CTRL", "ALT", "SHIFT", "RIGHT"), domain="time"),
    "time.scroll_current": _shortcut("time.scroll_current", "Scroll current time into view in Timeline", ("D",), domain="time"),
    "preview.toggle": _shortcut("preview.toggle", "Start or stop preview", ("SPACE",), domain="preview"),
    "preview.snapshot.take": _shortcut("preview.snapshot.take", "Take snapshot in slot 1", ("SHIFT", "F5"), domain="preview"),
    "preview.snapshot.show": _shortcut("preview.snapshot.show", "Display snapshot from slot 1", ("F5",), domain="preview"),
    "preview.fast.off": _shortcut("preview.fast.off", "Set Fast Previews to Off", ("CTRL", "ALT", "1"), domain="preview"),
    "preview.fast.adaptive": _shortcut("preview.fast.adaptive", "Set Fast Previews to Adaptive Resolution", ("CTRL", "ALT", "2"), domain="preview"),
    "preview.fast.draft": _shortcut("preview.fast.draft", "Set Fast Previews to Draft", ("CTRL", "ALT", "3"), domain="preview"),
    "preview.fast.fast_draft": _shortcut("preview.fast.fast_draft", "Set Fast Previews to Fast Draft", ("CTRL", "ALT", "4"), domain="preview"),
    "preview.fast.wireframe": _shortcut("preview.fast.wireframe", "Set Fast Previews to Wireframe", ("CTRL", "ALT", "5"), domain="preview"),

    # Viewer and timeline display.
    "view.zoom.in": _shortcut("view.zoom.in", "Zoom in active Composition, Layer, or Footage panel", ("PERIOD",), domain="view"),
    "view.zoom.out": _shortcut("view.zoom.out", "Zoom out active Composition, Layer, or Footage panel", ("COMMA",), domain="view"),
    "view.zoom.100": _shortcut("view.zoom.100", "Zoom active viewer to 100 percent", ("SLASH",), domain="view"),
    "view.zoom.fit": _shortcut("view.zoom.fit", "Zoom active viewer to fit", ("SHIFT", "SLASH"), domain="view"),
    "view.zoom.fit100": _shortcut("view.zoom.fit100", "Zoom active viewer up to 100 percent to fit", ("ALT", "SLASH"), domain="view"),
    "timeline.zoom.in": _shortcut("timeline.zoom.in", "Zoom in Timeline time scale", ("EQUALS",), domain="view"),
    "timeline.zoom.out": _shortcut("timeline.zoom.out", "Zoom out Timeline time scale", ("MINUS",), domain="view"),
    "timeline.zoom.frame_toggle": _shortcut("timeline.zoom.frame_toggle", "Toggle Timeline single-frame zoom", ("SEMICOLON",), domain="view"),
    "timeline.zoom.fit_toggle": _shortcut("timeline.zoom.fit_toggle", "Toggle Timeline full-duration zoom", ("SHIFT", "SEMICOLON"), domain="view"),
    "view.safe_zones.toggle": _shortcut("view.safe_zones.toggle", "Show or hide safe zones", ("APOSTROPHE",), domain="view"),
    "view.grid.toggle": _shortcut("view.grid.toggle", "Show or hide grid", ("CTRL", "APOSTROPHE"), domain="view"),
    "view.rulers.toggle": _shortcut("view.rulers.toggle", "Show or hide rulers", ("CTRL", "R"), domain="view"),
    "view.guides.toggle": _shortcut("view.guides.toggle", "Show or hide guides", ("CTRL", "SEMICOLON"), domain="view"),
    "view.layer_controls.toggle": _shortcut("view.layer_controls.toggle", "Show or hide layer controls", ("CTRL", "SHIFT", "H"), domain="view"),

    # Footage access. Dialog-opening commands are UI-only; actual insertion is scoped mutation.
    "footage.import.dialog": _shortcut("footage.import.dialog", "Open Import File dialog", ("CTRL", "I"), domain="footage"),
    "footage.import_multiple.dialog": _shortcut("footage.import_multiple.dialog", "Open Import Multiple Files dialog", ("CTRL", "ALT", "I"), domain="footage"),
    "footage.replace.dialog": _shortcut(
        "footage.replace.dialog", "Open Replace Footage dialog for selected Project item", ("CTRL", "H"),
        requires_target=True, domain="footage",
    ),
    "footage.proxy.dialog": _shortcut(
        "footage.proxy.dialog", "Open Set Proxy dialog for selected footage item", ("CTRL", "ALT", "P"),
        requires_target=True, domain="footage",
    ),
    "footage.add_to_active_comp": _shortcut(
        "footage.add_to_active_comp", "Add selected Project items to most recently active composition", ("CTRL", "SLASH"),
        impact="project_mutation", mutation_kinds=("footage", "layer_structure"), requires_target=True, domain="footage",
    ),

    # Effects and animation presets.
    "effects.delete_all": _shortcut(
        "effects.delete_all", "Delete all effects from selected layers", ("CTRL", "SHIFT", "E"),
        impact="project_mutation", mutation_kinds=("effect",), requires_target=True, domain="effect",
    ),
    "effects.apply_recent": _shortcut(
        "effects.apply_recent", "Apply most recently applied effect to selected layers", ("CTRL", "ALT", "SHIFT", "E"),
        impact="project_mutation", mutation_kinds=("effect",), requires_target=True, domain="effect",
    ),
    "preset.apply_recent": _shortcut(
        "preset.apply_recent", "Apply most recently applied animation preset to selected layers", ("CTRL", "ALT", "SHIFT", "F"),
        impact="project_mutation", mutation_kinds=("generic",), requires_target=True, domain="effect",
    ),

    # Layer creation, selection, timing, and structure.
    "layer.new.solid": _shortcut(
        "layer.new.solid", "Create new solid layer", ("CTRL", "Y"), impact="project_mutation",
        mutation_kinds=("layer_structure",), domain="layer",
    ),
    "layer.new.null": _shortcut(
        "layer.new.null", "Create new null layer", ("CTRL", "ALT", "SHIFT", "Y"), impact="project_mutation",
        mutation_kinds=("layer_structure",), domain="layer",
    ),
    "layer.new.adjustment": _shortcut(
        "layer.new.adjustment", "Create new adjustment layer", ("CTRL", "ALT", "Y"), impact="project_mutation",
        mutation_kinds=("layer_structure",), domain="layer",
    ),
    "layer.select.next": _shortcut("layer.select.next", "Select next layer in stacking order", ("CTRL", "DOWN"), domain="layer"),
    "layer.select.previous": _shortcut("layer.select.previous", "Select previous layer in stacking order", ("CTRL", "UP"), domain="layer"),
    "layer.select.extend_next": _shortcut("layer.select.extend_next", "Extend selection to next layer", ("CTRL", "SHIFT", "DOWN"), domain="layer"),
    "layer.select.extend_previous": _shortcut("layer.select.extend_previous", "Extend selection to previous layer", ("CTRL", "SHIFT", "UP"), domain="layer"),
    "layer.select.none": _shortcut("layer.select.none", "Deselect all layers", ("CTRL", "SHIFT", "A"), domain="layer"),
    "layer.columns.parent.toggle": _shortcut("layer.columns.parent.toggle", "Show or hide Parent column", ("SHIFT", "F4"), domain="layer"),
    "layer.columns.switches_modes.toggle": _shortcut("layer.columns.switches_modes.toggle", "Show or hide Layer Switches and Modes columns", ("F4",), domain="layer"),
    "layer.settings.open": _shortcut(
        "layer.settings.open", "Open settings dialog for selected solid, light, camera, null, or adjustment layer", ("CTRL", "SHIFT", "Y"),
        requires_target=True, domain="layer",
    ),
    "layer.split": _shortcut(
        "layer.split", "Split selected layers at current time", ("CTRL", "SHIFT", "D"), impact="project_mutation",
        mutation_kinds=("layer_timing", "layer_structure"), requires_target=True, domain="layer",
    ),
    "layer.precompose": _shortcut(
        "layer.precompose", "Precompose selected layers", ("CTRL", "SHIFT", "C"), impact="project_mutation",
        mutation_kinds=("composition", "layer_structure"), requires_target=True, domain="layer",
    ),
    "layer.reverse_time": _shortcut(
        "layer.reverse_time", "Reverse selected layers in time", ("CTRL", "ALT", "R"), impact="project_mutation",
        mutation_kinds=("layer_timing",), requires_target=True, domain="layer",
    ),
    "layer.time_remap.enable": _shortcut(
        "layer.time_remap.enable", "Enable time remapping for selected layers", ("CTRL", "ALT", "T"), impact="project_mutation",
        mutation_kinds=("layer_timing", "keyframe"), requires_target=True, domain="layer",
    ),
    "layer.in_to_current": _shortcut(
        "layer.in_to_current", "Move selected layer In point to current time", ("LBRACKET",), impact="project_mutation",
        mutation_kinds=("layer_timing",), requires_target=True, domain="layer",
    ),
    "layer.out_to_current": _shortcut(
        "layer.out_to_current", "Move selected layer Out point to current time", ("RBRACKET",), impact="project_mutation",
        mutation_kinds=("layer_timing",), requires_target=True, domain="layer",
    ),
    "layer.trim_in_to_current": _shortcut(
        "layer.trim_in_to_current", "Trim selected layer In point to current time", ("ALT", "LBRACKET"), impact="project_mutation",
        mutation_kinds=("layer_timing",), requires_target=True, domain="layer",
    ),
    "layer.trim_out_to_current": _shortcut(
        "layer.trim_out_to_current", "Trim selected layer Out point to current time", ("ALT", "RBRACKET"), impact="project_mutation",
        mutation_kinds=("layer_timing",), requires_target=True, domain="layer",
    ),
    "layer.move_in_to_comp_start": _shortcut(
        "layer.move_in_to_comp_start", "Move selected layers so In point is at composition start", ("ALT", "HOME"),
        impact="project_mutation", mutation_kinds=("layer_timing",), requires_target=True, domain="layer",
    ),
    "layer.move_out_to_comp_end": _shortcut(
        "layer.move_out_to_comp_end", "Move selected layers so Out point is at composition end", ("ALT", "END"),
        impact="project_mutation", mutation_kinds=("layer_timing",), requires_target=True, domain="layer",
    ),
    "layer.lock": _shortcut(
        "layer.lock", "Lock selected layers", ("CTRL", "L"), impact="project_mutation",
        mutation_kinds=("generic",), requires_target=True, domain="layer",
    ),
    "layer.unlock_all": _shortcut(
        "layer.unlock_all", "Unlock all layers", ("CTRL", "SHIFT", "L"), impact="project_mutation",
        mutation_kinds=("generic",), domain="layer",
    ),
    "layer.fit.comp": _shortcut(
        "layer.fit.comp", "Scale and reposition selected layers to fit composition", ("CTRL", "ALT", "F"),
        impact="project_mutation", mutation_kinds=("transform",), requires_target=True, domain="layer",
    ),
    "layer.fit.width": _shortcut(
        "layer.fit.width", "Scale selected layers to fit composition width", ("CTRL", "ALT", "SHIFT", "H"),
        impact="project_mutation", mutation_kinds=("transform",), requires_target=True, domain="layer",
    ),
    "layer.fit.height": _shortcut(
        "layer.fit.height", "Scale selected layers to fit composition height", ("CTRL", "ALT", "SHIFT", "G"),
        impact="project_mutation", mutation_kinds=("transform",), requires_target=True, domain="layer",
    ),

    # Timeline property reveal commands.
    "property.anchor.reveal": _shortcut("property.anchor.reveal", "Reveal Anchor Point on selected layer", ("A",), requires_target=True, domain="property"),
    "property.audio_levels.reveal": _shortcut("property.audio_levels.reveal", "Reveal Audio Levels on selected layer", ("L",), requires_target=True, domain="property"),
    "property.mask_feather.reveal": _shortcut("property.mask_feather.reveal", "Reveal Mask Feather on selected layer", ("F",), requires_target=True, domain="property"),
    "property.mask_path.reveal": _shortcut("property.mask_path.reveal", "Reveal Mask Path on selected layer", ("M",), requires_target=True, domain="property"),
    "property.mask_opacity.reveal": _sequence("property.mask_opacity.reveal", "Reveal Mask Opacity on selected layer", ("T", "T"), requires_target=True, domain="property"),
    "property.opacity.reveal": _shortcut("property.opacity.reveal", "Reveal Opacity on selected layer", ("T",), requires_target=True, domain="property"),
    "property.position.reveal": _shortcut("property.position.reveal", "Reveal Position on selected layer", ("P",), requires_target=True, domain="property"),
    "property.rotation.reveal": _shortcut("property.rotation.reveal", "Reveal Rotation and Orientation on selected layer", ("R",), requires_target=True, domain="property"),
    "property.scale.reveal": _shortcut("property.scale.reveal", "Reveal Scale on selected layer", ("S",), requires_target=True, domain="property"),
    "property.time_remap.reveal": _sequence("property.time_remap.reveal", "Reveal Time Remap on selected layer", ("R", "R"), requires_target=True, domain="property"),
    "property.missing_effects.reveal": _sequence("property.missing_effects.reveal", "Reveal instances of missing effects", ("F", "F"), requires_target=True, domain="property"),
    "property.effects.reveal": _shortcut("property.effects.reveal", "Reveal Effects group on selected layer", ("E",), requires_target=True, domain="property"),
    "property.masks.reveal": _sequence("property.masks.reveal", "Reveal all mask property groups on selected layer", ("M", "M"), requires_target=True, domain="property"),
    "property.material_options.reveal": _sequence("property.material_options.reveal", "Reveal Material Options on selected layer", ("A", "A"), requires_target=True, domain="property"),
    "property.expressions.reveal": _sequence("property.expressions.reveal", "Reveal properties with expressions", ("E", "E"), requires_target=True, domain="property"),
    "property.keyframed.reveal": _shortcut("property.keyframed.reveal", "Reveal properties with keyframes", ("U",), requires_target=True, domain="property"),
    "property.modified.reveal": _sequence("property.modified.reveal", "Reveal modified properties", ("U", "U"), requires_target=True, domain="property"),
    "property.paint_roto_puppet.reveal": _sequence("property.paint_roto_puppet.reveal", "Reveal paint, Roto Brush, and Puppet properties", ("P", "P"), requires_target=True, domain="property"),
    "property.audio_waveform.reveal": _sequence("property.audio_waveform.reveal", "Reveal audio waveform", ("L", "L"), requires_target=True, domain="property"),
    "property.selected.reveal": _sequence("property.selected.reveal", "Show only selected properties and groups", ("S", "S"), requires_target=True, domain="property"),
    "property.position.dialog": _shortcut("property.position.dialog", "Open Position dialog for selected layer", ("CTRL", "SHIFT", "P"), requires_target=True, domain="property"),
    "property.rotation.dialog": _shortcut("property.rotation.dialog", "Open Rotation dialog for selected layer", ("CTRL", "SHIFT", "R"), requires_target=True, domain="property"),
    "property.opacity.dialog": _shortcut("property.opacity.dialog", "Open Opacity dialog for selected layer", ("CTRL", "SHIFT", "O"), requires_target=True, domain="property"),
    "property.auto_orientation.dialog": _shortcut("property.auto_orientation.dialog", "Open Auto-Orientation dialog for selected layer", ("CTRL", "ALT", "O"), requires_target=True, domain="property"),
    "property.center_layers_in_view": _shortcut(
        "property.center_layers_in_view", "Center selected layers in current view", ("CTRL", "HOME"), impact="project_mutation",
        mutation_kinds=("transform",), requires_target=True, domain="property",
    ),
    "property.center_anchor_in_content": _shortcut(
        "property.center_anchor_in_content", "Center anchor point in visible layer content", ("CTRL", "ALT", "HOME"),
        impact="project_mutation", mutation_kinds=("transform",), requires_target=True, domain="property",
    ),

    # Masks.
    "mask.new": _shortcut(
        "mask.new", "Create a new mask on the selected layer", ("CTRL", "SHIFT", "N"),
        impact="project_mutation", mutation_kinds=("mask",), requires_target=True, domain="mask",
    ),
    "mask.free_transform": _shortcut("mask.free_transform", "Enter Free Transform mode for selected mask", ("CTRL", "T"), requires_target=True, domain="mask"),
    "mask.shape_dialog": _shortcut("mask.shape_dialog", "Open Mask Shape dialog for selected mask", ("CTRL", "SHIFT", "M"), requires_target=True, domain="mask"),
    "mask.feather_dialog": _shortcut("mask.feather_dialog", "Open Mask Feather dialog for selected mask", ("CTRL", "SHIFT", "F"), requires_target=True, domain="mask"),
    "mask.invert": _shortcut(
        "mask.invert", "Invert selected mask", ("CTRL", "SHIFT", "I"), impact="project_mutation",
        mutation_kinds=("mask",), requires_target=True, domain="mask",
    ),

    # Keyframes and Graph Editor.
    "graph_editor.toggle": _shortcut("graph_editor.toggle", "Toggle Graph Editor and layer-bar modes", ("SHIFT", "F3"), domain="keyframe"),
    "keyframe.select_visible_all": _shortcut("keyframe.select_visible_all", "Select all visible keyframes and properties", ("CTRL", "ALT", "A"), domain="keyframe"),
    "keyframe.deselect_all": _shortcut("keyframe.deselect_all", "Deselect keyframes, properties, and groups", ("SHIFT", "F2"), domain="keyframe"),
    "keyframe.move.previous_frame": _shortcut(
        "keyframe.move.previous_frame", "Move selected keyframes one frame earlier", ("ALT", "LEFT"), impact="project_mutation",
        mutation_kinds=("keyframe",), requires_target=True, domain="keyframe",
    ),
    "keyframe.move.next_frame": _shortcut(
        "keyframe.move.next_frame", "Move selected keyframes one frame later", ("ALT", "RIGHT"), impact="project_mutation",
        mutation_kinds=("keyframe",), requires_target=True, domain="keyframe",
    ),
    "keyframe.move.previous_10": _shortcut(
        "keyframe.move.previous_10", "Move selected keyframes ten frames earlier", ("ALT", "SHIFT", "LEFT"), impact="project_mutation",
        mutation_kinds=("keyframe",), requires_target=True, domain="keyframe",
    ),
    "keyframe.move.next_10": _shortcut(
        "keyframe.move.next_10", "Move selected keyframes ten frames later", ("ALT", "SHIFT", "RIGHT"), impact="project_mutation",
        mutation_kinds=("keyframe",), requires_target=True, domain="keyframe",
    ),
    "keyframe.interpolation.dialog": _shortcut("keyframe.interpolation.dialog", "Open Keyframe Interpolation dialog", ("CTRL", "ALT", "K"), requires_target=True, domain="keyframe"),
    "keyframe.interpolation.hold_auto": _shortcut(
        "keyframe.interpolation.hold_auto", "Toggle selected keyframes between Hold and Auto Bezier", ("CTRL", "ALT", "H"),
        impact="project_mutation", mutation_kinds=("keyframe",), requires_target=True, domain="keyframe",
    ),
    "keyframe.ease": _shortcut(
        "keyframe.ease", "Easy Ease selected keyframes", ("F9",), impact="project_mutation",
        mutation_kinds=("keyframe",), requires_target=True, domain="keyframe",
    ),
    "keyframe.ease_in": _shortcut(
        "keyframe.ease_in", "Easy Ease In selected keyframes", ("SHIFT", "F9"), impact="project_mutation",
        mutation_kinds=("keyframe",), requires_target=True, domain="keyframe",
    ),
    "keyframe.ease_out": _shortcut(
        "keyframe.ease_out", "Easy Ease Out selected keyframes", ("CTRL", "SHIFT", "F9"), impact="project_mutation",
        mutation_kinds=("keyframe",), requires_target=True, domain="keyframe",
    ),
    "keyframe.velocity.dialog": _shortcut("keyframe.velocity.dialog", "Open Keyframe Velocity dialog", ("CTRL", "SHIFT", "K"), requires_target=True, domain="keyframe"),
    "keyframe.paste_reverse": _shortcut(
        "keyframe.paste_reverse", "Reverse-paste copied keyframes", ("CTRL", "SHIFT", "V"), impact="project_mutation",
        mutation_kinds=("keyframe",), requires_target=True, domain="keyframe",
    ),

    # Text.
    "text.new_layer": _shortcut(
        "text.new_layer", "Create new text layer", ("CTRL", "ALT", "SHIFT", "T"), impact="project_mutation",
        mutation_kinds=("text", "layer_structure"), domain="text",
    ),
    "text.align.left": _shortcut(
        "text.align.left", "Align selected horizontal text left", ("CTRL", "SHIFT", "L"), impact="project_mutation",
        mutation_kinds=("text",), requires_target=True, domain="text",
    ),
    "text.align.center": _shortcut(
        "text.align.center", "Align selected text center", ("CTRL", "SHIFT", "C"), impact="project_mutation",
        mutation_kinds=("text",), requires_target=True, domain="text",
    ),
    "text.align.right": _shortcut(
        "text.align.right", "Align selected horizontal text right", ("CTRL", "SHIFT", "R"), impact="project_mutation",
        mutation_kinds=("text",), requires_target=True, domain="text",
    ),

    # 3D layer/view commands.
    "view3d.front": _shortcut("view3d.front", "Switch to 3D View 1 / Front", ("F10",), domain="3d"),
    "view3d.custom": _shortcut("view3d.custom", "Switch to 3D View 2 / Custom View", ("F11",), domain="3d"),
    "view3d.camera": _shortcut("view3d.camera", "Switch to 3D View 3 / Active Camera", ("F12",), domain="3d"),
    "layer3d.new_light": _shortcut(
        "layer3d.new_light", "Create new light layer", ("CTRL", "ALT", "SHIFT", "L"), impact="project_mutation",
        mutation_kinds=("layer_structure",), domain="3d",
    ),
    "layer3d.new_camera": _shortcut(
        "layer3d.new_camera", "Create new camera layer", ("CTRL", "ALT", "SHIFT", "C"), impact="project_mutation",
        mutation_kinds=("layer_structure",), domain="3d",
    ),
    "gizmo.position": _shortcut("gizmo.position", "Switch to Position gizmo", ("4",), domain="3d"),
    "gizmo.scale": _shortcut("gizmo.scale", "Switch to Scale gizmo", ("5",), domain="3d"),
    "gizmo.rotation": _shortcut("gizmo.rotation", "Switch to Rotation gizmo", ("6",), domain="3d"),
    "camera.look_at_selected": _shortcut(
        "camera.look_at_selected", "Move camera and point of interest to look at selected 3D layers", ("CTRL", "ALT", "SHIFT", "BACKSLASH"),
        impact="project_mutation", mutation_kinds=("transform",), requires_target=True, domain="3d",
    ),
    "camera.look_at_all": _shortcut(
        "camera.look_at_all", "With camera tool selected, look at all 3D layers", ("CTRL", "SHIFT", "F"),
        impact="project_mutation", mutation_kinds=("transform",), requires_target=True, domain="3d",
    ),
}


_BASELINE_PLANNER_COMMANDS = (
    "quick_apply.open",
    "tool.selection",
    "focus.comp_timeline.toggle",
    "panel.project.toggle",
    "panel.effects_presets.toggle",
    "panel.effect_controls.open",
    "property.position.reveal",
    "property.scale.reveal",
    "property.rotation.reveal",
    "property.opacity.reveal",
    "property.keyframed.reveal",
    "time.frame.forward",
    "time.frame.backward",
    "preview.toggle",
)
_STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "this", "that", "selected", "select",
    "after", "effects", "layer", "layers", "current", "open", "show", "make", "use", "video",
}


def get_ae_command(key: str) -> AECommandRecipe:
    normalized = key.strip().lower()
    if normalized not in AE_COMMANDS:
        raise KeyError(f"unknown After Effects command: {key!r}")
    return AE_COMMANDS[normalized]


def command_catalog(*, domain: str | None = None, impact: str | None = None) -> tuple[dict[str, Any], ...]:
    recipes = AE_COMMANDS.values()
    if domain is not None:
        recipes = (recipe for recipe in recipes if recipe.domain == domain)
    if impact is not None:
        recipes = (recipe for recipe in recipes if recipe.impact == impact)
    return tuple(recipe.as_dict() for recipe in recipes)


def command_keys_for_goal(goal: str, *, limit: int = 32) -> tuple[str, ...]:
    """Return a compact relevant subset so a larger command library does not slow the warm loop."""
    if limit < 1:
        return ()
    tokens = {
        token for token in re.findall(r"[a-z0-9]+", goal.lower())
        if len(token) >= 2 and token not in _STOPWORDS
    }
    scored: list[tuple[int, str]] = []
    for key, recipe in AE_COMMANDS.items():
        key_text = key.replace(".", " ")
        haystack = f"{key_text} {recipe.description.lower()} {recipe.domain}"
        score = sum(2 if token in key_text else 1 for token in tokens if token in haystack)
        if score:
            scored.append((score, key))
    scored.sort(key=lambda item: (-item[0], item[1]))

    ordered = [key for _, key in scored]
    ordered.extend(_BASELINE_PLANNER_COMMANDS)
    result: list[str] = []
    seen: set[str] = set()
    for key in ordered:
        if key in seen:
            continue
        seen.add(key)
        result.append(key)
        if len(result) >= limit:
            break
    return tuple(result)
