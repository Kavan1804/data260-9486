from __future__ import annotations

from typing import Any, Dict, TypedDict


class AgentState(TypedDict, total=False):
    title: str; content: str; email: str; strict: bool; task: str; llm: Any
    planner_proposal: Dict[str, Any]; reviewer_feedback: Dict[str, Any]
    turn_count: int; turn_ceiling: int; validation_error: str; outcome: str

GraphState = AgentState


def initialize_state(title: str, content: str, email: str, task: str, llm: Any, strict: bool = True, turn_ceiling: int = 10) -> AgentState:
    return AgentState(title=title, content=content, email=email, strict=strict, task=task, llm=llm,
                      planner_proposal={}, reviewer_feedback={}, turn_count=0, turn_ceiling=turn_ceiling)

