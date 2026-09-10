from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from .planner import PlannedAction
from .policy import classify_action_impact


MUTATION_KIND_TERMS: dict[str, tuple[str, ...]] = {
    "transform": ("position", "scale", "rotation", "opacity", "anchor point"),
    "keyframe": ("keyframe", "key frame"),
    "effect": ("effect", "effects & presets", "gaussian blur"),
    "mask": ("mask",),
    "layer_timing": ("trim", "split", "in point", "out point", "time remap", "stretch"),
    "text": ("text layer", "source text", "text content"),
    "shape": ("shape layer",),
    "composition": ("composition", "comp settings", "precompose", "pre-compose"),
    "footage": ("footage", "source replacement", "replace source"),
    "layer_structure": ("duplicate layer", "new layer", "adjustment layer", "null object"),
}
ALLOWED_MUTATION_KINDS = frozenset((*MUTATION_KIND_TERMS.keys(), "generic"))


@dataclass(frozen=True)
class ScopeDecision:
    allowed: bool
    mutation_kinds: tuple[str, ...]
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RollbackVerification:
    ok: bool
    changed_fraction: float
    max_changed_fraction: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EditingTaskContract:
    """Explicit authority for a bounded, undoable After Effects editing task."""

    task_id: str
    goal: str
    allowed_mutations: tuple[str, ...]
    target_terms: tuple[str, ...] = ()
    max_mutations: int = 1
    rollback_keys: tuple[str, ...] = ("CTRL", "Z")
    rollback_max_changed_fraction: float = 0.08

    def __post_init__(self) -> None:
        task_id = self.task_id.strip()
        goal = self.goal.strip()
        mutations = tuple(dict.fromkeys(value.strip().lower() for value in self.allowed_mutations if value.strip()))
        targets = tuple(dict.fromkeys(value.strip().lower() for value in self.target_terms if value.strip()))
        rollback_keys = tuple(value.strip().upper() for value in self.rollback_keys if value.strip())
        if not task_id:
            raise ValueError("editing task_id must not be empty")
        if not goal:
            raise ValueError("editing task goal must not be empty")
        if not mutations:
            raise ValueError("editing task must authorize at least one mutation kind")
        unknown = sorted(set(mutations).difference(ALLOWED_MUTATION_KINDS))
        if unknown:
            raise ValueError(f"unknown editing mutation kinds: {', '.join(unknown)}")
        if self.max_mutations < 1 or self.max_mutations > 32:
            raise ValueError("max_mutations must be between 1 and 32")
        if not rollback_keys:
            raise ValueError("rollback_keys must not be empty")
        if not 0.0 <= self.rollback_max_changed_fraction <= 1.0:
            raise ValueError("rollback_max_changed_fraction must be between 0 and 1")
        object.__setattr__(self, "task_id", task_id)
        object.__setattr__(self, "goal", goal)
        object.__setattr__(self, "allowed_mutations", mutations)
        object.__setattr__(self, "target_terms", targets)
        object.__setattr__(self, "rollback_keys", rollback_keys)

    def planner_scope(self) -> str:
        targets = ", ".join(self.target_terms) if self.target_terms else "any target explicitly named by the task goal"
        return (
            f"task_id={self.task_id}; allowed mutation kinds={', '.join(self.allowed_mutations)}; "
            f"allowed target terms={targets}; maximum committed mutations={self.max_mutations}; "
            "destructive actions are not authorized"
        )

    def authorize(self, plan: PlannedAction, *, committed_mutations: int) -> ScopeDecision:
        impact = classify_action_impact(plan)
        if impact == "destructive":
            return ScopeDecision(False, (), "destructive action is outside the M4 editing task contract")
        if impact != "project_mutation":
            return ScopeDecision(True, (), "action does not consume project-mutation scope")
        if committed_mutations >= self.max_mutations:
            return ScopeDecision(False, (), "editing task mutation budget is exhausted")

        kinds = classify_mutation_kinds(plan)
        unauthorized = tuple(kind for kind in kinds if kind not in self.allowed_mutations)
        if unauthorized:
            return ScopeDecision(
                False,
                kinds,
                "mutation kind is outside the editing task contract: " + ", ".join(unauthorized),
            )

        if self.target_terms:
            target_text = " ".join(
                value for value in (plan.target, plan.destination, plan.expected) if value
            ).lower()
            if not any(term in target_text for term in self.target_terms):
                return ScopeDecision(False, kinds, "planned mutation does not name an authorized task target")

        return ScopeDecision(True, kinds, "project mutation is inside the explicit editing task scope")


def classify_mutation_kinds(plan: PlannedAction) -> tuple[str, ...]:
    if classify_action_impact(plan) != "project_mutation":
        return ()
    text = " ".join(
        value for value in (plan.target, plan.destination, plan.expected) if value
    ).lower()
    kinds = tuple(kind for kind, terms in MUTATION_KIND_TERMS.items() if any(term in text for term in terms))
    return kinds or ("generic",)


def visual_change_fraction(before: np.ndarray, after: np.ndarray, *, pixel_threshold: float = 15.0) -> float:
    if before.shape != after.shape:
        return 1.0
    if before.size == 0:
        return 1.0
    delta = np.abs(after.astype(np.int16) - before.astype(np.int16)).mean(axis=2)
    return float((delta >= pixel_threshold).mean())


def verify_rollback(
    before: np.ndarray,
    after: np.ndarray,
    *,
    max_changed_fraction: float = 0.08,
) -> RollbackVerification:
    changed = visual_change_fraction(before, after)
    return RollbackVerification(
        ok=changed <= max_changed_fraction,
        changed_fraction=changed,
        max_changed_fraction=max_changed_fraction,
    )
