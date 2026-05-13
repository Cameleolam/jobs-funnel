from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.graph.nodes import (
    flag_human_node,
    grade_route,
    persist_node,
    retrieve_cv_context_node,
    retrieve_decisions_node,
    score_node,
    select_cv_node,
    self_critique_node,
)
from scripts.graph.state import initial_state
from scripts.llm.providers import provider_from_key
from scripts.scoring import provider_keys_from_env


def _providers_from_env(
    config: dict[str, Any],
    *,
    allow_review: bool = True,
) -> tuple[Any, Any | None]:
    base_key, review_key = provider_keys_from_env()
    base = provider_from_key(base_key, config)
    review = provider_from_key(review_key, config) if allow_review and review_key else None
    return base, review


def _initial_graph_state(
    job: dict[str, Any],
    system_prompt: str,
    config: dict[str, Any],
    root: Path,
    base_provider: Any,
    review_provider: Any | None,
):
    state = initial_state(job)
    state["system_prompt"] = system_prompt
    state["config"] = config
    state["root"] = root
    state["base_provider"] = base_provider
    if review_provider is not None:
        state["review_provider"] = review_provider
    return state


def run_filter_flow(
    job: dict[str, Any],
    system_prompt: str,
    config: dict[str, Any],
    root: Path,
    base_provider: Any | None = None,
    review_provider: Any | None = None,
    allow_review: bool = True,
) -> dict[str, Any]:
    if not allow_review:
        review_provider = None
    if base_provider is None:
        base_provider, env_review = _providers_from_env(config, allow_review=allow_review)
        if review_provider is None:
            review_provider = env_review

    state = _initial_graph_state(
        job,
        system_prompt,
        config,
        root,
        base_provider,
        review_provider,
    )
    state = retrieve_decisions_node(state)
    state = retrieve_cv_context_node(state)
    state = score_node(state)

    while True:
        route = grade_route(state)
        if route == "critique":
            state = self_critique_node(state)
            continue
        if route == "flag_human":
            state = flag_human_node(state)
            break
        state = select_cv_node(state)
        break

    state = persist_node(state)
    return state["assessment"]


def build_filter_graph():
    try:
        from langgraph.graph import END, StateGraph
    except ImportError as exc:
        raise RuntimeError("langgraph is not installed. Run `pip install -e .`.") from exc

    from scripts.graph.state import FilterState

    graph = StateGraph(FilterState)
    graph.add_node("retrieve_decisions", retrieve_decisions_node)
    graph.add_node("retrieve_cv_context", retrieve_cv_context_node)
    graph.add_node("score", score_node)
    graph.add_node("self_critique", self_critique_node)
    graph.add_node("flag_human", flag_human_node)
    graph.add_node("select_cv", select_cv_node)
    graph.add_node("persist", persist_node)

    graph.set_entry_point("retrieve_decisions")
    graph.add_edge("retrieve_decisions", "retrieve_cv_context")
    graph.add_edge("retrieve_cv_context", "score")
    graph.add_conditional_edges(
        "score",
        grade_route,
        {
            "critique": "self_critique",
            "flag_human": "flag_human",
            "select_cv": "select_cv",
        },
    )
    graph.add_conditional_edges(
        "self_critique",
        grade_route,
        {
            "critique": "flag_human",
            "flag_human": "flag_human",
            "select_cv": "select_cv",
        },
    )
    graph.add_edge("flag_human", "persist")
    graph.add_edge("select_cv", "persist")
    graph.add_edge("persist", END)
    return graph.compile()


def run_filter_graph(
    job: dict[str, Any],
    system_prompt: str,
    config: dict[str, Any],
    root: Path,
    base_provider: Any | None = None,
    review_provider: Any | None = None,
    allow_review: bool = True,
) -> dict[str, Any]:
    if not allow_review:
        review_provider = None
    if base_provider is None:
        base_provider, env_review = _providers_from_env(config, allow_review=allow_review)
        if review_provider is None:
            review_provider = env_review

    state = _initial_graph_state(
        job,
        system_prompt,
        config,
        root,
        base_provider,
        review_provider,
    )
    final_state = build_filter_graph().invoke(state)
    return final_state["assessment"]
