from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .ae_commands import get_ae_command
from .planner import PlannedAction


REVERSIBLE_DRAG_TERMS = (
    "playhead", "current-time indicator", "scrollbar", "scroll bar",
    "panel divider", "panel splitter",
)
DESTRUCTIVE_TERMS = (
    "delete", "remove", "purge", "overwrite", "replace footage",
    "close project", "quit", "exit", "save", "export", "render",
    "collect files",
)
PROJECT_MUTATION_TERMS = (
    "layer", "keyframe", "effect", "mask", "composition", "comp ",
    "position", "scale", "rotation", "opacity", "anchor point", "trim",
    "split", "time remap", "text layer", "shape layer", "footage",
)
REVERSIBLE_CLICK_TERMS = (
    "menu", "dropdown", "tab", "panel", "search field", "search box",
    "timeline ruler", "toolbar", "workspace",
)
REVERSIBLE_UI_EXPECTATION_TERMS = (
    "is selected", "is highlighted", "field is focused", "field is active",
    "is expanded", "is collapsed", "dropdown is visible", "menu is open",
    "submenu is visible", "panel is active", "panel is focused",
    "property is visible", "property is revealed", "properties are visible",
    "properties are revealed", "tool is active", "search contains",
    "search field contains", "search box contains", "query is visible",
    "quick apply contains",
)


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    impact: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TaskPolicy:
    name: str
    allow_project_mutation: bool = False
    allow_destructive: bool = False
    allow_ambiguous: bool = False

    @classmethod
    def ui_proof(cls) -> "TaskPolicy":
        return cls(name="ui_proof")

    @classmethod
    def editing(cls, *, allow_destructive: bool = False) -> "TaskPolicy":
        return cls(
            name="editing",
            allow_project_mutation=True,
            allow_destructive=allow_destructive,
            allow_ambiguous=False,
        )

    def authorize(self, plan: PlannedAction) -> PolicyDecision:
        impact = classify_action_impact(plan)
        if impact == "destructive" and not self.allow_destructive:
            return PolicyDecision(False, impact, "destructive/non-transactional actions are not authorized by this task policy")
        if impact == "project_mutation" and not self.allow_project_mutation:
            return PolicyDecision(False, impact, "project mutation is not authorized by this task policy")
        if impact == "ambiguous" and not self.allow_ambiguous:
            return PolicyDecision(False, impact, "action impact is ambiguous and policy fails closed")
        return PolicyDecision(True, impact, f"{impact} action is authorized by policy {self.name}")


def classify_action_impact(plan: PlannedAction) -> str:
    if plan.status != "act" or plan.action_type is None:
        return "none"

    action = plan.action_type
    if action == "ae_command":
        if not plan.command:
            return "ambiguous"
        try:
            return get_ae_command(plan.command).impact
        except KeyError:
            return "ambiguous"

    text = " ".join(filter(None, (plan.target, plan.destination, plan.expected))).lower()
    expected = plan.expected.lower()
    if any(term in text for term in DESTRUCTIVE_TERMS):
        return "destructive"

    if action in {"wait", "move", "scroll"}:
        return "reversible_ui"
    if action == "keypress":
        keys = tuple(key.upper() for key in plan.keys)
        if keys in {("ESC",), ("ESCAPE",), ("HOME",), ("UP",), ("DOWN",), ("LEFT",), ("RIGHT",)}:
            return "reversible_ui"
        if any(term in expected for term in REVERSIBLE_UI_EXPECTATION_TERMS):
            return "reversible_ui"
        return "project_mutation"
    if action == "drag":
        if any(term in text for term in REVERSIBLE_DRAG_TERMS):
            return "reversible_ui"
        return "project_mutation"
    if action in {"click", "double_click"}:
        if any(term in expected for term in REVERSIBLE_UI_EXPECTATION_TERMS):
            return "reversible_ui"
        if any(term in text for term in PROJECT_MUTATION_TERMS):
            return "project_mutation"
        if any(term in text for term in REVERSIBLE_CLICK_TERMS):
            return "reversible_ui"
        return "ambiguous"
    if action == "type":
        if any(term in expected for term in REVERSIBLE_UI_EXPECTATION_TERMS):
            return "reversible_ui"
        return "project_mutation"
    return "ambiguous"
