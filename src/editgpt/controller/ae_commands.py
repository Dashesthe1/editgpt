from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


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
    source: str = "Adobe After Effects keyboard shortcut"

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
) -> AECommandRecipe:
    return AECommandRecipe(
        key=key,
        description=description,
        transport="shortcut",
        impact=impact,
        mutation_kinds=mutation_kinds,
        requires_target=requires_target,
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
) -> AECommandRecipe:
    return AECommandRecipe(
        key=key,
        description=description,
        transport="shortcut_sequence",
        impact=impact,
        mutation_kinds=mutation_kinds,
        requires_target=requires_target,
        steps=tuple(AECommandStep("keypress", keys=(value,)) for value in keys),
    )


AE_COMMANDS: dict[str, AECommandRecipe] = {
    "property.anchor.reveal": _shortcut(
        "property.anchor.reveal", "Reveal Anchor Point on selected layer", ("A",), requires_target=True
    ),
    "property.position.reveal": _shortcut(
        "property.position.reveal", "Reveal Position on selected layer", ("P",), requires_target=True
    ),
    "property.scale.reveal": _shortcut(
        "property.scale.reveal", "Reveal Scale on selected layer", ("S",), requires_target=True
    ),
    "property.rotation.reveal": _shortcut(
        "property.rotation.reveal", "Reveal Rotation/Orientation on selected layer", ("R",), requires_target=True
    ),
    "property.opacity.reveal": _shortcut(
        "property.opacity.reveal", "Reveal Opacity on selected layer", ("T",), requires_target=True
    ),
    "property.effects.reveal": _shortcut(
        "property.effects.reveal", "Reveal Effects group on selected layer", ("E",), requires_target=True
    ),
    "property.mask_path.reveal": _shortcut(
        "property.mask_path.reveal", "Reveal Mask Path on selected layer", ("M",), requires_target=True
    ),
    "property.masks.reveal": _sequence(
        "property.masks.reveal", "Reveal all mask property groups on selected layer", ("M", "M"), requires_target=True
    ),
    "property.keyframed.reveal": _shortcut(
        "property.keyframed.reveal", "Reveal properties with keyframes on selected layer", ("U",), requires_target=True
    ),
    "property.modified.reveal": _sequence(
        "property.modified.reveal", "Reveal modified properties on selected layer", ("U", "U"), requires_target=True
    ),
    "mask.new": _shortcut(
        "mask.new",
        "Create a new mask on the selected layer",
        ("CTRL", "SHIFT", "N"),
        impact="project_mutation",
        mutation_kinds=("mask",),
        requires_target=True,
    ),
    "mask.free_transform": _shortcut(
        "mask.free_transform", "Enter Free Transform mode for selected mask", ("CTRL", "T"), requires_target=True
    ),
    "mask.shape_dialog": _shortcut(
        "mask.shape_dialog", "Open Mask Shape dialog for selected mask", ("CTRL", "SHIFT", "M"), requires_target=True
    ),
    "mask.feather_dialog": _shortcut(
        "mask.feather_dialog", "Open Mask Feather dialog for selected mask", ("CTRL", "SHIFT", "F"), requires_target=True
    ),
    "property.position.dialog": _shortcut(
        "property.position.dialog", "Open Position dialog for selected layer", ("CTRL", "SHIFT", "P"), requires_target=True
    ),
    "property.rotation.dialog": _shortcut(
        "property.rotation.dialog", "Open Rotation dialog for selected layer", ("CTRL", "SHIFT", "R"), requires_target=True
    ),
    "property.opacity.dialog": _shortcut(
        "property.opacity.dialog", "Open Opacity dialog for selected layer", ("CTRL", "SHIFT", "O"), requires_target=True
    ),
    "quick_apply.open": _shortcut(
        "quick_apply.open",
        "Open After Effects Quick Apply search",
        ("CTRL", "ENTER"),
        requires_target=False,
    ),
}


def get_ae_command(key: str) -> AECommandRecipe:
    normalized = key.strip().lower()
    if normalized not in AE_COMMANDS:
        raise KeyError(f"unknown After Effects command: {key!r}")
    return AE_COMMANDS[normalized]


def command_catalog() -> tuple[dict[str, Any], ...]:
    return tuple(recipe.as_dict() for recipe in AE_COMMANDS.values())
