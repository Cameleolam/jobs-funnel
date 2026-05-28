(function () {
  var graphEl = document.getElementById("clusters-graph");
  var emptyEl = document.getElementById("clusters-empty");
  var form = document.getElementById("clusters-controls");
  var summaryEl = document.getElementById("clusters-summary");
  var selectionEl = document.getElementById("clusters-selection");
  var clustersListEl = document.getElementById("clusters-list");
  var network = null;
  var latestGraph = null;

  var palette = [
    "#2563eb",
    "#16a34a",
    "#ca8a04",
    "#dc2626",
    "#7c3aed",
    "#0891b2",
    "#be185d",
    "#4b5563",
  ];

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function hashColor(value) {
    var text = String(value || "unknown");
    var hash = 0;
    for (var i = 0; i < text.length; i += 1) {
      hash = ((hash << 5) - hash) + text.charCodeAt(i);
      hash |= 0;
    }
    return palette[Math.abs(hash) % palette.length];
  }

  function currentColorBy() {
    return form.elements.color_by.value || "decision";
  }

  function nodeGroup(node) {
    return node[currentColorBy()] || "unknown";
  }

  function nodeLabel(node) {
    if (node.label) return node.label;
    if (node.company && node.title) return node.company + "\n" + node.title;
    return node.title || node.company || ("Job " + node.id);
  }

  function nodeSize(node) {
    if (node.size != null && Number.isFinite(Number(node.size))) {
      return Number(node.size);
    }
    var score = Number(node.score || node.fit_score || 0);
    if (!score) return 16;
    var normalized = score > 10 ? score / 10 : score;
    return Math.max(9, Math.min(18, 8 + normalized));
  }

  function formatDate(value) {
    if (!value) return "";
    return String(value).slice(0, 10);
  }

  function formatScore(value) {
    if (value == null || value === "") return "";
    var score = Number(value);
    if (!Number.isFinite(score)) return "";
    return Math.round(score) + (score > 10 ? "/100" : "/10");
  }

  function formatSimilarity(value) {
    if (value == null) return "";
    return Math.round(Number(value) * 100) + "%";
  }

  function destroyNetwork() {
    if (network && typeof network.destroy === "function") {
      network.destroy();
    }
    network = null;
  }

  function showEmpty(message) {
    destroyNetwork();
    emptyEl.textContent = message;
    emptyEl.hidden = false;
    graphEl.hidden = true;
  }

  function showGraph() {
    emptyEl.textContent = "";
    emptyEl.hidden = true;
    graphEl.hidden = false;
  }

  function graphParams() {
    var params = new URLSearchParams(new FormData(form));
    params.set("hide_same_company_edges",
      form.elements.hide_same_company_edges.checked ? "true" : "false");
    return params;
  }

  function renderSummary(graph) {
    var meta = graph.meta || {};
    var bits = [
      (meta.node_count || graph.nodes.length) + " jobs",
      (meta.edge_count || graph.edges.length) + " links",
      (meta.cluster_count || graph.clusters.length) + " clusters",
    ];
    if (meta.params) {
      if (meta.params.company_cap !== "all") {
        bits.push(meta.params.company_cap + "/company cap");
      }
      if (meta.params.hide_same_company_edges) {
        bits.push("same-company links hidden");
      }
    }
    summaryEl.textContent = bits.join(" - ");
  }

  function renderSelection(node) {
    if (!node) {
      selectionEl.innerHTML = "<h3>Selection</h3><p class=\"text-muted\">No selection.</p>";
      return;
    }

    var neighbors = (latestGraph.edges || [])
      .filter(function (edge) {
        return edge.source === node.id || edge.target === node.id;
      })
      .map(function (edge) {
        var otherId = edge.source === node.id ? edge.target : edge.source;
        var other = latestGraph.nodeById[String(otherId)];
        return { edge: edge, node: other };
      })
      .filter(function (item) { return item.node; })
      .sort(function (a, b) {
        return Number(b.edge.similarity) - Number(a.edge.similarity);
      })
      .slice(0, 6);

    var rows = neighbors.map(function (item) {
      return "<li><span>" + escapeHtml(nodeLabel(item.node).replace(/\n/g, " - ")) +
        "</span><strong>" + escapeHtml(formatSimilarity(item.edge.similarity)) + "</strong></li>";
    }).join("");

    selectionEl.innerHTML =
      "<h3>" + escapeHtml(node.title || node.label || ("Job " + node.id)) + "</h3>" +
      "<dl class=\"cluster-job-meta\">" +
      "<div><dt>Company</dt><dd>" + escapeHtml(node.company || "") + "</dd></div>" +
      "<div><dt>Score</dt><dd>" + escapeHtml(formatScore(node.score || node.fit_score)) + "</dd></div>" +
      "<div><dt>Decision</dt><dd>" + escapeHtml(node.decision || "") + "</dd></div>" +
      "<div><dt>Source</dt><dd>" + escapeHtml(node.source || "") + "</dd></div>" +
      "<div><dt>Date</dt><dd>" + escapeHtml(formatDate(node.crawled_at || node.analyzed_at)) + "</dd></div>" +
      "</dl>" +
      "<a class=\"btn btn-secondary btn-sm\" href=\"/jobs/" + encodeURIComponent(node.id) + "\">Open job</a>" +
      "<h4>Nearest jobs</h4>" +
      "<ul class=\"cluster-neighbor-list\">" + (rows || "<li class=\"text-muted\">No linked jobs.</li>") + "</ul>";
  }

  function renderClusters(graph) {
    if (!graph.clusters.length) {
      clustersListEl.innerHTML = "<p class=\"text-muted\">No clusters.</p>";
      return;
    }

    clustersListEl.innerHTML = graph.clusters.map(function (cluster) {
      var terms = (cluster.terms || []).slice(0, 4).map(escapeHtml).join(", ");
      return "<button type=\"button\" class=\"cluster-list-item\" data-cluster-id=\"" +
        escapeHtml(cluster.id) + "\">" +
        "<span><strong>" + escapeHtml(cluster.label || ("Cluster " + cluster.id)) + "</strong>" +
        "<small>" + escapeHtml(cluster.size || 0) + " jobs" +
        (terms ? " - " + terms : "") + "</small></span>" +
        "</button>";
    }).join("");
  }

  function renderClusterTree(cluster) {
    var clusterNodes = (cluster.node_ids || [])
      .map(function (id) { return latestGraph.nodeById[String(id)]; })
      .filter(Boolean);
    var byCompany = {};
    clusterNodes.forEach(function (node) {
      var company = node.company || "Unknown";
      if (!byCompany[company]) byCompany[company] = [];
      byCompany[company].push(node);
    });

    var companyRows = Object.keys(byCompany)
      .sort(function (a, b) {
        return byCompany[b].length - byCompany[a].length || a.localeCompare(b);
      })
      .map(function (company) {
        var jobs = byCompany[company]
          .sort(function (a, b) {
            return Number(b.score || 0) - Number(a.score || 0);
          })
          .map(function (node) {
            return "<li><a href=\"/jobs/" + encodeURIComponent(node.id) + "\">" +
              escapeHtml(node.title || node.label || ("Job " + node.id)) + "</a>" +
              "<span>" + escapeHtml(formatScore(node.score || node.fit_score)) + "</span></li>";
          })
          .join("");
        return "<details class=\"cluster-tree-company\" open>" +
          "<summary>" + escapeHtml(company) + " (" + byCompany[company].length + ")</summary>" +
          "<ul>" + jobs + "</ul>" +
          "</details>";
      })
      .join("");

    selectionEl.innerHTML =
      "<h3>" + escapeHtml(cluster.label || "Cluster") + "</h3>" +
      "<p class=\"text-muted\">" + escapeHtml(cluster.size || 0) + " jobs</p>" +
      "<div class=\"cluster-tree\">" + companyRows + "</div>";
  }

  function renderGraph(graph) {
    latestGraph = graph;
    latestGraph.nodeById = {};
    graph.nodes.forEach(function (node) {
      latestGraph.nodeById[String(node.id)] = node;
    });

    renderSummary(graph);
    renderClusters(graph);
    renderSelection(null);

    if (graph.meta && graph.meta.unavailable_reason) {
      showEmpty(graph.meta.unavailable_reason);
      return;
    }
    if (!graph.nodes.length) {
      showEmpty("No analyzed jobs with calibration embeddings match these filters.");
      return;
    }
    if (!window.vis || !window.vis.Network) {
      showEmpty("Graph library unavailable.");
      return;
    }
    showGraph();
    destroyNetwork();

    var nodes = new window.vis.DataSet(graph.nodes.map(function (node) {
      var group = nodeGroup(node);
      var color = hashColor(group);
      return {
        id: node.id,
        label: nodeLabel(node),
        value: nodeSize(node),
        title: escapeHtml(node.title || ""),
        color: {
          background: color,
          border: color,
          highlight: { background: color, border: "#111827" },
        },
        font: { color: "#111827", size: 13 },
      };
    }));

    var edges = new window.vis.DataSet(graph.edges.map(function (edge) {
      return {
        id: String(edge.source) + "-" + String(edge.target),
        from: edge.source,
        to: edge.target,
        value: Math.max(1, Math.round(Number(edge.similarity || 0.8) * 4)),
        title: formatSimilarity(edge.similarity),
        color: { color: "rgba(107, 114, 128, 0.42)" },
      };
    }));

    network = new window.vis.Network(graphEl, { nodes: nodes, edges: edges }, {
      autoResize: true,
      layout: { improvedLayout: false },
      interaction: { hover: true, multiselect: true },
      nodes: { shape: "dot", scaling: { min: 12, max: 34 } },
      edges: { smooth: false },
      physics: {
        solver: "forceAtlas2Based",
        stabilization: { iterations: 120 },
        forceAtlas2Based: { gravitationalConstant: -45, springLength: 90 },
      },
    });

    network.on("selectNode", function (params) {
      var selected = params.nodes[0];
      renderSelection(latestGraph.nodeById[String(selected)]);
    });
    network.on("deselectNode", function () {
      renderSelection(null);
    });
  }

  function loadGraph() {
    summaryEl.textContent = "Loading...";
    showEmpty("Loading graph...");

    fetch("/api/clusters/graph?" + graphParams().toString())
      .then(function (response) {
        if (!response.ok) throw new Error("Request failed: " + response.status);
        return response.json();
      })
      .then(renderGraph)
      .catch(function (error) {
        var message = error && error.message ? error.message : "unknown error";
        console.error("Cluster graph render failed", error);
        summaryEl.textContent = "Unavailable";
        showEmpty("Cluster graph unavailable: " + message);
      });
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    loadGraph();
  });

  form.addEventListener("change", loadGraph);

  clustersListEl.addEventListener("click", function (event) {
    var button = event.target.closest(".cluster-list-item");
    if (!button || !network || !latestGraph) return;
    var cluster = latestGraph.clusters.find(function (item) {
      return String(item.id) === button.dataset.clusterId;
    });
    if (!cluster) return;
    network.selectNodes(cluster.node_ids || []);
    if (cluster.node_ids && cluster.node_ids.length) {
      network.fit({ nodes: cluster.node_ids, animation: true });
    }
    renderClusterTree(cluster);
  });

  loadGraph();
})();
