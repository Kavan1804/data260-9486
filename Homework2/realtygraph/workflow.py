from __future__ import annotations
from langgraph.graph import END, START, StateGraph
from .nodes import planner_node, reviewer_node, supervisor_node
from .router import router_logic
from .state import AgentState

def build_workflow():
    graph = StateGraph(AgentState)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("planner", planner_node)
    graph.add_node("reviewer", reviewer_node)
    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges("supervisor", router_logic, {"planner": "planner", "END": END})
    graph.add_edge("planner", "reviewer")
    graph.add_edge("reviewer", "supervisor")
    return graph.compile()
