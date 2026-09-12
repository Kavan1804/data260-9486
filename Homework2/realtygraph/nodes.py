from __future__ import annotations
from typing import Any, Dict
from pydantic import BaseModel, ValidationError, field_validator
from .state import AgentState

class PlannerProposal(BaseModel):
    tags: list[str]
    summary: str
    @field_validator("tags")
    @classmethod
    def exactly_three_strings(cls, value: list[str]) -> list[str]:
        if len(value) != 3 or any(not isinstance(x, str) or not 3 <= len(x) <= 30 for x in value):
            raise ValueError("tags must contain exactly three strings, each 3-30 characters")
        return value
    @field_validator("summary")
    @classmethod
    def max_25_words(cls, value: str) -> str:
        if len(value.split()) > 25:
            raise ValueError("summary must contain at most 25 words")
        return value

def planner_node(state: AgentState) -> Dict[str, Any]:
    prompt = ("Return JSON only with exactly three tags (3-30 characters each) and a summary of at most 25 words. "
              f"Task: {state.get('task','')} Title: {state.get('title','')} Content: {state.get('content','')} "
              f"Email: {state.get('email','')} Previous validation error: {state.get('validation_error','none')}")
    try:
        proposal = state["llm"].generate_json(prompt)
        validated = PlannerProposal.model_validate(proposal)
        return {"planner_proposal": validated.model_dump(), "validation_error": ""}
    except Exception as error:
        return {"planner_proposal": {}, "validation_error": str(error)}

def reviewer_node(state: AgentState) -> Dict[str, Any]:
    if state.get("validation_error"):
        return {"reviewer_feedback": {"approved": False, "issues": [state["validation_error"]]}}
    try:
        PlannerProposal.model_validate(state.get("planner_proposal", {}))
        return {"reviewer_feedback": {"approved": True, "issues": []}, "outcome": "valid"}
    except ValidationError as error:
        return {"reviewer_feedback": {"approved": False, "issues": [str(error)]}}

def supervisor_node(state: AgentState) -> Dict[str, Any]:
    return {"turn_count": state.get("turn_count", 0) + 1}
