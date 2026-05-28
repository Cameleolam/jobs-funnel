from unittest.mock import MagicMock

from ui.services import cluster_graph


def test_normalize_graph_params_defaults_and_conservative_clamps():
    params = cluster_graph.normalize_graph_params(
        days="nope",
        limit="nope",
        threshold="nope",
        color_by="bad",
    )

    assert params == {
        "days": 30,
        "limit": 250,
        "threshold": 0.82,
        "color_by": "decision",
        "company_cap": 25,
        "hide_same_company_edges": True,
    }

    params = cluster_graph.normalize_graph_params(
        days="all",
        limit="all",
        threshold="1.5",
        color_by="source",
        company_cap="all",
        hide_same_company_edges="false",
    )

    assert params == {
        "days": "all",
        "limit": "all",
        "threshold": 1.0,
        "color_by": "source",
        "company_cap": "all",
        "hide_same_company_edges": False,
    }

    assert cluster_graph.normalize_graph_params(threshold="nan")["threshold"] == 0.82
    assert cluster_graph.normalize_graph_params(limit="999")["limit"] == 500


def test_build_graph_dedupes_thresholds_edges_and_clusters():
    rows = [
        {
            "id": 1,
            "title": "Backend Engineer",
            "company": "Acme",
            "fit_score": 8,
            "decision": "PASS",
            "source": "linkedin",
            "user_status": "interested",
            "crawled_at": "2026-05-01T10:00:00",
            "analyzed_at": "2026-05-01T11:00:00",
            "tags": ["python", "platform"],
        },
        {
            "id": 2,
            "title": "Senior Backend Developer",
            "company": "Beta",
            "fit_score": 6,
            "decision": "MAYBE",
            "source": "indeed",
            "user_status": None,
            "tags": ["python"],
        },
        {
            "id": 3,
            "title": "Product Manager",
            "company": "Gamma",
            "fit_score": 3,
            "decision": "SKIP",
            "source": "linkedin",
            "user_status": "dismissed",
            "tags": ["product"],
        },
    ]
    edge_rows = [
        {"source_id": 1, "target_id": 2, "similarity": 0.91},
        {"source_id": 2, "target_id": 1, "similarity": 0.89},
        {"source_id": 1, "target_id": 3, "similarity": 0.80},
        {"source_id": 3, "target_id": 3, "similarity": 1.0},
    ]

    graph = cluster_graph.build_graph(
        rows,
        edge_rows,
        cluster_graph.normalize_graph_params(threshold=0.82),
    )

    assert [node["label"] for node in graph["nodes"]] == [
        "Backend Engineer @ Acme",
        "Senior Backend Developer @ Beta",
        "Product Manager @ Gamma",
    ]
    assert graph["nodes"][0]["crawled_at"] == "2026-05-01T10:00:00"
    assert graph["nodes"][0]["analyzed_at"] == "2026-05-01T11:00:00"
    assert graph["nodes"][0]["size"] > graph["nodes"][2]["size"]
    assert graph["nodes"][0]["color_group"] == "PASS"
    assert graph["edges"] == [
        {"id": "1-2", "source": 1, "target": 2, "similarity": 0.91}
    ]
    assert graph["clusters"][0]["node_ids"] == [1, 2]
    assert graph["clusters"][0]["size"] == 2
    assert graph["clusters"][0]["label"] in {"python", "backend"}
    assert graph["clusters"][1]["node_ids"] == [3]
    assert graph["meta"]["node_count"] == 3
    assert graph["meta"]["edge_count"] == 1


def test_build_graph_can_hide_same_company_edges():
    rows = [
        {"id": 1, "title": "Backend Engineer", "company": "Acme", "fit_score": 8},
        {"id": 2, "title": "Platform Engineer", "company": "Acme", "fit_score": 7},
        {"id": 3, "title": "Data Engineer", "company": "Beta", "fit_score": 6},
    ]
    edge_rows = [
        {"source_id": 1, "target_id": 2, "similarity": 0.95},
        {"source_id": 1, "target_id": 3, "similarity": 0.90},
    ]

    graph = cluster_graph.build_graph(
        rows,
        edge_rows,
        cluster_graph.normalize_graph_params(hide_same_company_edges=True),
    )

    assert graph["edges"] == [
        {"id": "1-3", "source": 1, "target": 3, "similarity": 0.9}
    ]

    graph = cluster_graph.build_graph(
        rows,
        edge_rows,
        cluster_graph.normalize_graph_params(hide_same_company_edges=False),
    )

    assert [edge["id"] for edge in graph["edges"]] == ["1-2", "1-3"]


def test_get_cluster_graph_returns_empty_when_calibration_column_unavailable(monkeypatch):
    fetch_all = MagicMock()
    monkeypatch.setattr(cluster_graph.schema, "HAS_CALIBRATION_EMBEDDING_COLUMN", False)
    monkeypatch.setattr(cluster_graph, "fetch_all", fetch_all)

    graph = cluster_graph.get_cluster_graph()

    assert graph["nodes"] == []
    assert graph["edges"] == []
    assert graph["clusters"] == []
    assert graph["meta"]["unavailable_reason"] == "embedding_calibration_unavailable"
    fetch_all.assert_not_called()


def test_get_cluster_graph_queries_pgvector_edges_without_returning_embeddings(monkeypatch):
    node_rows = [
        {
            "id": 1,
            "title": "Backend Engineer",
            "company": "Acme",
            "fit_score": 8,
            "decision": "PASS",
            "source": "linkedin",
            "user_status": None,
            "crawled_at": "2026-05-01T10:00:00",
            "analyzed_at": "2026-05-01T11:00:00",
            "tags": [],
        },
        {
            "id": 2,
            "title": "Backend Developer",
            "company": "Beta",
            "fit_score": 6,
            "decision": "MAYBE",
            "source": "indeed",
            "user_status": None,
            "tags": [],
        },
    ]
    edge_rows = [{"source_id": 1, "target_id": 2, "similarity": 0.9}]
    fetch_all = MagicMock(side_effect=[node_rows, edge_rows])
    monkeypatch.setattr(cluster_graph.schema, "HAS_CALIBRATION_EMBEDDING_COLUMN", True)
    monkeypatch.setattr(cluster_graph, "TABLE", "jobs_test")
    monkeypatch.setattr(cluster_graph, "fetch_all", fetch_all)

    graph = cluster_graph.get_cluster_graph(days=30, limit=100, threshold=0.82)

    node_sql, node_params = fetch_all.call_args_list[0].args
    edge_sql, edge_params = fetch_all.call_args_list[1].args
    assert "FROM jobs_test" in node_sql
    assert "ROW_NUMBER() OVER" in node_sql
    assert "company_rank <= %s" in node_sql
    assert "crawled_at" in node_sql
    assert "analyzed_at" in node_sql
    assert "embedding_calibration IS NOT NULL" in node_sql
    assert "embedding_calibration <=>" not in node_sql
    assert node_params == (30, 25, 100)
    assert "embedding_calibration <=>" in edge_sql
    assert "1 - (a.embedding_calibration <=> b.embedding_calibration)" in edge_sql
    assert "JOIN selected b ON a.id < b.id" in edge_sql
    assert "normalized_company" in edge_sql
    assert edge_params == (30, 25, 100, 0.82)
    assert "embedding_calibration" not in graph["nodes"][0]
    assert graph["edges"] == [
        {"id": "1-2", "source": 1, "target": 2, "similarity": 0.9}
    ]


def test_get_cluster_graph_supports_all_limit_and_no_company_cap(monkeypatch):
    fetch_all = MagicMock(side_effect=[[], []])
    monkeypatch.setattr(cluster_graph.schema, "HAS_CALIBRATION_EMBEDDING_COLUMN", True)
    monkeypatch.setattr(cluster_graph, "TABLE", "jobs_test")
    monkeypatch.setattr(cluster_graph, "fetch_all", fetch_all)

    graph = cluster_graph.get_cluster_graph(
        days="all",
        limit="all",
        company_cap="all",
        hide_same_company_edges=False,
    )

    node_sql, node_params = fetch_all.call_args_list[0].args
    edge_sql, edge_params = fetch_all.call_args_list[1].args
    assert "LIMIT %s" not in node_sql
    assert "LIMIT %s" not in edge_sql
    assert "company_rank <= %s" not in node_sql
    assert "company_rank <= %s" not in edge_sql
    assert "a.normalized_company <> b.normalized_company" not in edge_sql
    assert node_params == ()
    assert edge_params == (0.82,)
    assert graph["meta"]["params"]["limit"] == "all"
    assert graph["meta"]["params"]["company_cap"] == "all"
