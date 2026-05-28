from fastapi.testclient import TestClient
from pathlib import Path

from ui.server import app

CLUSTERS_JS = Path("ui/static/clusters.js").read_text(encoding="utf-8")
STYLES = Path("ui/static/styles.css").read_text(encoding="utf-8")


def test_clusters_page_renders_graph_shell():
    response = TestClient(app).get("/clusters")

    assert response.status_code == 200
    assert "Job Clusters" in response.text
    assert 'id="clusters-graph"' in response.text
    assert 'src="/static/clusters.js"' in response.text
    assert "vis-network@9.1.9" in response.text
    assert 'integrity="sha384-' in response.text
    assert 'crossorigin="anonymous"' in response.text
    assert '<option value="all">All</option>' in response.text
    assert 'name="company_cap"' in response.text
    assert 'name="hide_same_company_edges"' in response.text


def test_clusters_api_passes_filter_params_to_service(monkeypatch):
    from ui.routes import clusters

    calls = []

    def fake_graph(**kwargs):
        calls.append(kwargs)
        return {
            "nodes": [],
            "edges": [],
            "clusters": [],
            "meta": {"node_count": 0, "edge_count": 0},
        }

    monkeypatch.setattr(clusters.cluster_graph, "get_cluster_graph", fake_graph)

    response = TestClient(app).get(
        "/api/clusters/graph?days=all&limit=all&threshold=0.9&color_by=source"
        "&company_cap=10&hide_same_company_edges=false"
    )

    assert response.status_code == 200
    assert response.json()["meta"]["node_count"] == 0
    assert calls == [{
        "days": "all",
        "limit": "all",
        "threshold": "0.9",
        "color_by": "source",
        "company_cap": "10",
        "hide_same_company_edges": "false",
    }]


def test_clusters_api_accepts_empty_editable_filter_values(monkeypatch):
    from ui.routes import clusters

    calls = []

    def fake_graph(**kwargs):
        calls.append(kwargs)
        return {
            "nodes": [],
            "edges": [],
            "clusters": [],
            "meta": {"params": kwargs},
        }

    monkeypatch.setattr(clusters.cluster_graph, "get_cluster_graph", fake_graph)

    response = TestClient(app).get("/api/clusters/graph?limit=&threshold=")

    assert response.status_code == 200
    assert calls == [{
        "days": "30",
        "limit": "",
        "threshold": "",
        "color_by": "decision",
        "company_cap": "25",
        "hide_same_company_edges": "true",
    }]


def test_clusters_js_uses_project_score_scale_and_service_node_size():
    assert "node.size" in CLUSTERS_JS
    assert 'score > 10 ? "/100" : "/10"' in CLUSTERS_JS


def test_clusters_js_destroys_old_network_before_redraw():
    assert "function destroyNetwork()" in CLUSTERS_JS
    assert "network.destroy()" in CLUSTERS_JS


def test_clusters_js_disables_vis_improved_layout_and_reports_errors():
    assert "layout: { improvedLayout: false }" in CLUSTERS_JS
    assert "Cluster graph render failed" in CLUSTERS_JS
    assert "Cluster graph unavailable: " in CLUSTERS_JS


def test_clusters_js_keeps_vis_labels_plain_text():
    assert "multi: true" not in CLUSTERS_JS


def test_clusters_success_state_clears_loading_message():
    assert 'emptyEl.textContent = "";' in CLUSTERS_JS
    assert ".clusters-empty[hidden]" in STYLES


def test_clusters_js_sends_checkbox_state_and_renders_drilldown_tree():
    assert 'params.set("hide_same_company_edges"' in CLUSTERS_JS
    assert "renderClusterTree" in CLUSTERS_JS
    assert "cluster-tree" in CLUSTERS_JS
    assert "same-company links hidden" in CLUSTERS_JS
