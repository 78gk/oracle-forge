"""
LangGraph conductor: blueprint parity with fork README (phased nodes, same Toolbox-backed execution).

Set ``ORACLE_FORGE_USE_LANGGRAPH=false`` to run the linear pipeline without LangGraph.
"""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from .pipeline_runtime import OracleForgePipeline


class ConductorState(TypedDict, total=False):
    """Serializable graph state; pipeline lives in closure."""

    response: Optional[Dict[str, Any]]
    phase: Literal["setup", "route", "schema", "execute", "done"]


def run_with_langgraph(pipeline: OracleForgePipeline) -> Dict[str, Any]:
    """Compile and run the Oracle Forge graph; returns the same dict as sequential ``run_agent``."""

    def node_setup(state: ConductorState) -> ConductorState:
        early = pipeline.phase_setup()
        if early is not None:
            return {"response": early, "phase": "done"}
        return {"phase": "route"}

    def node_route(state: ConductorState) -> ConductorState:
        early = pipeline.phase_route()
        if early is not None:
            return {"response": early, "phase": "done"}
        return {"phase": "schema"}

    def node_schema(state: ConductorState) -> ConductorState:
        early = pipeline.phase_schema_and_global_plan()
        if early is not None:
            return {"response": early, "phase": "done"}
        return {"phase": "execute"}

    def node_execute(state: ConductorState) -> ConductorState:
        final = pipeline.phase_execute_and_merge()
        return {"response": final, "phase": "done"}

    def route_after_setup(state: ConductorState) -> str:
        if state.get("response") is not None:
            return END
        return "route"

    def route_after_route(state: ConductorState) -> str:
        if state.get("response") is not None:
            return END
        return "schema"

    def route_after_schema(state: ConductorState) -> str:
        if state.get("response") is not None:
            return END
        return "execute"

    graph = StateGraph(ConductorState)
    graph.add_node("setup", node_setup)
    graph.add_node("route", node_route)
    graph.add_node("schema", node_schema)
    graph.add_node("execute", node_execute)

    graph.add_edge(START, "setup")
    graph.add_conditional_edges("setup", route_after_setup, {"route": "route", END: END})
    graph.add_conditional_edges("route", route_after_route, {"schema": "schema", END: END})
    graph.add_conditional_edges("schema", route_after_schema, {"execute": "execute", END: END})
    graph.add_edge("execute", END)

    app = graph.compile()
    out = app.invoke({"phase": "setup"})
    resp = out.get("response")
    if not isinstance(resp, dict):
        raise RuntimeError("LangGraph conductor finished without a response payload")
    return resp
