from __future__ import annotations

from typing import Literal

from .state import GraphState


def router_logic(state: GraphState) -> Literal["planner", "END"]:
    if state.get("planner_proposal") and state.get("reviewer_feedback", {}).get("approved"):
        return "END"
    if state.get("turn_count", 0) >= state.get("turn_ceiling", 10):
        return "END"
    return "planner"

