"""Semantic cluster graph data service."""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from collections.abc import Mapping
from typing import Any

from ui import schema
from ui.config import TABLE
from ui.db import fetch_all


DEFAULT_DAYS = 30
DEFAULT_LIMIT = 250
DEFAULT_THRESHOLD = 0.82
DEFAULT_COLOR_BY = "decision"
DEFAULT_COMPANY_CAP = 25
DEFAULT_HIDE_SAME_COMPANY_EDGES = True

_ALLOWED_DAYS = (7, 30, 90)
_ALLOWED_LIMITS = (100, 250, 500)
_ALLOWED_COMPANY_CAPS = (10, 25, 50)
_ALLOWED_COLOR_BY = {"decision", "source", "user_status"}
_TITLE_STOPWORDS = {
    "and",
    "developer",
    "engineer",
    "for",
    "lead",
    "manager",
    "of",
    "senior",
    "software",
    "the",
}


def _bucket(value: Any, allowed: tuple[int, ...], default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if number <= allowed[0]:
        return allowed[0]
    if number >= allowed[-1]:
        return allowed[-1]
    lower = allowed[0]
    for option in allowed:
        if number == option:
            return option
        if number < option:
            return lower
        lower = option
    return default


def normalize_graph_params(
    days: Any = DEFAULT_DAYS,
    limit: Any = DEFAULT_LIMIT,
    threshold: Any = DEFAULT_THRESHOLD,
    color_by: Any = DEFAULT_COLOR_BY,
    company_cap: Any = DEFAULT_COMPANY_CAP,
    hide_same_company_edges: Any = DEFAULT_HIDE_SAME_COMPANY_EDGES,
) -> dict[str, Any]:
    if str(days).lower() == "all":
        normalized_days: int | str = "all"
    else:
        normalized_days = _bucket(days, _ALLOWED_DAYS, DEFAULT_DAYS)

    if str(limit).lower() == "all":
        normalized_limit: int | str = "all"
    else:
        normalized_limit = _bucket(limit, _ALLOWED_LIMITS, DEFAULT_LIMIT)

    if str(company_cap).lower() == "all":
        normalized_company_cap: int | str = "all"
    else:
        normalized_company_cap = _bucket(
            company_cap, _ALLOWED_COMPANY_CAPS, DEFAULT_COMPANY_CAP
        )

    try:
        normalized_threshold = float(threshold)
    except (TypeError, ValueError):
        normalized_threshold = DEFAULT_THRESHOLD
    else:
        if not math.isfinite(normalized_threshold) or normalized_threshold < 0:
            normalized_threshold = DEFAULT_THRESHOLD
        elif normalized_threshold > 1:
            normalized_threshold = 1.0

    normalized_color_by = str(color_by)
    if normalized_color_by not in _ALLOWED_COLOR_BY:
        normalized_color_by = DEFAULT_COLOR_BY

    if isinstance(hide_same_company_edges, bool):
        normalized_hide_same_company_edges = hide_same_company_edges
    else:
        normalized_hide_same_company_edges = str(hide_same_company_edges).lower() not in {
            "false",
            "0",
            "no",
            "off",
        }

    return {
        "days": normalized_days,
        "limit": normalized_limit,
        "threshold": round(normalized_threshold, 4),
        "color_by": normalized_color_by,
        "company_cap": normalized_company_cap,
        "hide_same_company_edges": normalized_hide_same_company_edges,
    }


def _empty_graph(params: dict[str, Any], unavailable_reason: str | None = None):
    meta = {
        "params": params,
        "node_count": 0,
        "edge_count": 0,
        "cluster_count": 0,
    }
    if unavailable_reason:
        meta["unavailable_reason"] = unavailable_reason
    return {"nodes": [], "edges": [], "clusters": [], "meta": meta}


def _row_value(row: Mapping[str, Any], key: str, default: Any = None) -> Any:
    return row.get(key, default)


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _node_label(row: Mapping[str, Any]) -> str:
    title = str(_row_value(row, "title") or "Untitled").strip()
    company = str(_row_value(row, "company") or "Unknown").strip()
    return f"{title} @ {company}"


def _node_size(score: Any) -> float:
    value = _coerce_float(score)
    if value is None:
        return 8.0
    normalized = value / 10 if value > 10 else value
    normalized = min(10.0, max(0.0, normalized))
    return round(8.0 + normalized, 2)


def _normalized_company(value: Any) -> str:
    return str(value or "unknown").strip().lower() or "unknown"


def _tags(value: Any) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = [part.strip() for part in value.split(",")]
    if not isinstance(value, list):
        return []
    return [str(tag).strip().lower() for tag in value if str(tag).strip()]


def _cluster_label(nodes: list[dict[str, Any]]) -> str:
    tag_counts = Counter(tag for node in nodes for tag in node.get("tags", []))
    if tag_counts:
        return tag_counts.most_common(1)[0][0]

    title_counts: Counter[str] = Counter()
    for node in nodes:
        for token in re.findall(r"[A-Za-z][A-Za-z0-9]+", node.get("title", "").lower()):
            if token not in _TITLE_STOPWORDS:
                title_counts[token] += 1
    if title_counts:
        return title_counts.most_common(1)[0][0]
    return "cluster"


def _connected_components(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> list[list[int]]:
    order = {node["id"]: index for index, node in enumerate(nodes)}
    adjacency: dict[int, set[int]] = {node["id"]: set() for node in nodes}
    for edge in edges:
        source = edge["source"]
        target = edge["target"]
        adjacency[source].add(target)
        adjacency[target].add(source)

    components: list[list[int]] = []
    seen: set[int] = set()
    for node in nodes:
        node_id = node["id"]
        if node_id in seen:
            continue
        stack = [node_id]
        component: list[int] = []
        seen.add(node_id)
        while stack:
            current = stack.pop()
            component.append(current)
            for next_id in sorted(adjacency[current], key=order.get, reverse=True):
                if next_id not in seen:
                    seen.add(next_id)
                    stack.append(next_id)
        components.append(sorted(component, key=order.get))

    return sorted(components, key=lambda item: (-len(item), order[item[0]]))


def build_graph(
    rows: list[Mapping[str, Any]],
    edge_rows: list[Mapping[str, Any]],
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_params = params or normalize_graph_params()
    nodes: list[dict[str, Any]] = []
    node_by_id: dict[int, dict[str, Any]] = {}

    for row in rows:
        node_id = _coerce_int(_row_value(row, "id"))
        if node_id is None:
            continue
        tags = _tags(_row_value(row, "tags"))
        color_group = _row_value(row, normalized_params["color_by"]) or "unknown"
        node = {
            "id": node_id,
            "label": _node_label(row),
            "title": _row_value(row, "title") or "",
            "company": _row_value(row, "company") or "",
            "score": _row_value(row, "fit_score"),
            "size": _node_size(_row_value(row, "fit_score")),
            "decision": _row_value(row, "decision"),
            "source": _row_value(row, "source"),
            "user_status": _row_value(row, "user_status"),
            "crawled_at": _row_value(row, "crawled_at"),
            "analyzed_at": _row_value(row, "analyzed_at"),
            "tags": tags,
            "color_group": color_group,
        }
        nodes.append(node)
        node_by_id[node_id] = node

    best_edges: dict[tuple[int, int], float] = {}
    threshold = normalized_params["threshold"]
    for edge_row in edge_rows:
        source = _coerce_int(_row_value(edge_row, "source_id"))
        target = _coerce_int(_row_value(edge_row, "target_id"))
        similarity = _coerce_float(_row_value(edge_row, "similarity"))
        if (
            source is None
            or target is None
            or source == target
            or source not in node_by_id
            or target not in node_by_id
            or similarity is None
            or similarity < threshold
        ):
            continue
        if (
            normalized_params["hide_same_company_edges"]
            and _normalized_company(node_by_id[source]["company"])
            == _normalized_company(node_by_id[target]["company"])
        ):
            continue
        edge_key = tuple(sorted((source, target)))
        if similarity > best_edges.get(edge_key, -1):
            best_edges[edge_key] = similarity

    edges = [
        {
            "id": f"{source}-{target}",
            "source": source,
            "target": target,
            "similarity": round(similarity, 4),
        }
        for (source, target), similarity in best_edges.items()
    ]
    edges.sort(key=lambda edge: (-edge["similarity"], edge["source"], edge["target"]))

    components = _connected_components(nodes, edges)
    clusters = []
    for index, component in enumerate(components, start=1):
        cluster_nodes = [node_by_id[node_id] for node_id in component]
        clusters.append({
            "id": f"cluster-{index}",
            "node_ids": component,
            "size": len(component),
            "label": _cluster_label(cluster_nodes),
        })

    return {
        "nodes": nodes,
        "edges": edges,
        "clusters": clusters,
        "meta": {
            "params": normalized_params,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "cluster_count": len(clusters),
        },
    }


def _date_clause(days: int | str) -> tuple[str, tuple[Any, ...]]:
    if days == "all":
        return "", ()
    return "AND analyzed_at >= NOW() - make_interval(days => %s)", (days,)


def _company_cap_clause(company_cap: int | str) -> tuple[str, tuple[Any, ...]]:
    if company_cap == "all":
        return "", ()
    return "WHERE company_rank <= %s", (company_cap,)


def _limit_clause(limit: int | str) -> tuple[str, tuple[Any, ...]]:
    if limit == "all":
        return "", ()
    return "LIMIT %s", (limit,)


def _node_query(params: dict[str, Any]) -> tuple[str, tuple[Any, ...]]:
    date_clause, date_params = _date_clause(params["days"])
    company_cap_clause, company_cap_params = _company_cap_clause(params["company_cap"])
    limit_clause, limit_params = _limit_clause(params["limit"])
    query = f"""
        WITH ranked AS (
            SELECT
                id, title, company, source, fit_score, decision, user_status,
                tags, crawled_at, analyzed_at,
                LOWER(COALESCE(NULLIF(company, ''), 'unknown')) AS normalized_company,
                ROW_NUMBER() OVER (
                    PARTITION BY LOWER(COALESCE(NULLIF(company, ''), 'unknown'))
                    ORDER BY analyzed_at DESC NULLS LAST, id DESC
                ) AS company_rank
            FROM {TABLE}
            WHERE status = 'analyzed'
              AND embedding_calibration IS NOT NULL
              {date_clause}
        ),
        selected AS (
            SELECT *
            FROM ranked
            {company_cap_clause}
            ORDER BY analyzed_at DESC NULLS LAST, id DESC
            {limit_clause}
        )
        SELECT
            id, title, company, source, fit_score, decision, user_status,
            tags, crawled_at, analyzed_at
        FROM selected
        ORDER BY analyzed_at DESC NULLS LAST, id DESC
    """
    return query, (*date_params, *company_cap_params, *limit_params)


def _edge_query(params: dict[str, Any]) -> tuple[str, tuple[Any, ...]]:
    date_clause, date_params = _date_clause(params["days"])
    company_cap_clause, company_cap_params = _company_cap_clause(params["company_cap"])
    limit_clause, limit_params = _limit_clause(params["limit"])
    same_company_clause = (
        "AND a.normalized_company <> b.normalized_company"
        if params["hide_same_company_edges"]
        else ""
    )
    query = f"""
        WITH ranked AS (
            SELECT
                id,
                company,
                embedding_calibration,
                LOWER(COALESCE(NULLIF(company, ''), 'unknown')) AS normalized_company,
                ROW_NUMBER() OVER (
                    PARTITION BY LOWER(COALESCE(NULLIF(company, ''), 'unknown'))
                    ORDER BY analyzed_at DESC NULLS LAST, id DESC
                ) AS company_rank,
                analyzed_at
            FROM {TABLE}
            WHERE status = 'analyzed'
              AND embedding_calibration IS NOT NULL
              {date_clause}
        ),
        selected AS (
            SELECT *
            FROM ranked
            {company_cap_clause}
            ORDER BY analyzed_at DESC NULLS LAST, id DESC
            {limit_clause}
        )
        SELECT
            a.id AS source_id,
            b.id AS target_id,
            1 - (a.embedding_calibration <=> b.embedding_calibration) AS similarity
        FROM selected a
        JOIN selected b ON a.id < b.id
        WHERE 1 - (a.embedding_calibration <=> b.embedding_calibration) >= %s
          {same_company_clause}
        ORDER BY similarity DESC, source_id, target_id
    """
    return query, (*date_params, *company_cap_params, *limit_params, params["threshold"])


def get_cluster_graph(
    days: Any = DEFAULT_DAYS,
    limit: Any = DEFAULT_LIMIT,
    threshold: Any = DEFAULT_THRESHOLD,
    color_by: Any = DEFAULT_COLOR_BY,
    company_cap: Any = DEFAULT_COMPANY_CAP,
    hide_same_company_edges: Any = DEFAULT_HIDE_SAME_COMPANY_EDGES,
) -> dict[str, Any]:
    params = normalize_graph_params(
        days,
        limit,
        threshold,
        color_by,
        company_cap,
        hide_same_company_edges,
    )
    if not schema.HAS_CALIBRATION_EMBEDDING_COLUMN:
        return _empty_graph(params, "embedding_calibration_unavailable")

    node_query, node_params = _node_query(params)
    edge_query, edge_params = _edge_query(params)
    rows = fetch_all(node_query, node_params)
    edge_rows = fetch_all(edge_query, edge_params)
    return build_graph(rows, edge_rows, params)
