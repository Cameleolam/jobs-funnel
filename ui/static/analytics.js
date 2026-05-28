(function () {
  var panels = document.querySelectorAll("[data-analytics-endpoint]");
  if (!panels.length) return;

  function setStatus(panel, text) {
    var status = panel.querySelector("[data-analytics-status]");
    if (status) status.textContent = text;
  }

  function renderEmptyState(panel, message) {
    var empty = panel.querySelector("[data-analytics-empty]");
    if (!empty) return;
    empty.textContent = message;
    empty.hidden = false;
  }

  function hideEmptyState(panel) {
    var empty = panel.querySelector("[data-analytics-empty]");
    if (empty) empty.hidden = true;
  }

  function clearRendered(panel) {
    var rendered = panel.querySelector("[data-analytics-rendered]");
    if (rendered) rendered.remove();
  }

  function appendText(parent, tag, className, text) {
    var element = document.createElement(tag);
    if (className) element.className = className;
    element.textContent = text;
    parent.appendChild(element);
    return element;
  }

  function formatRate(value) {
    var number = Number(value);
    if (!Number.isFinite(number)) return "0%";
    return Math.round(number * 100) + "%";
  }

  function renderCounters(container, summary) {
    var counters = document.createElement("div");
    counters.className = "scoring-counters";
    [
      ["Total", "total"],
      ["Applied", "applied"],
      ["Dismissed", "dismissed"],
      ["Pending", "pending_review"],
      ["Review", "needs_human_review"],
      ["Low confidence", "low_confidence"],
    ].forEach(function (item) {
      var counter = document.createElement("div");
      counter.className = "scoring-counter";
      appendText(counter, "span", "scoring-counter-value", String(summary[item[1]] || 0));
      appendText(counter, "span", "scoring-counter-label", item[0]);
      counters.appendChild(counter);
    });
    container.appendChild(counters);
  }

  function renderBuckets(container, buckets) {
    var section = document.createElement("div");
    section.className = "scoring-section";
    appendText(section, "h4", null, "Score buckets");

    (buckets || []).forEach(function (bucket) {
      var row = document.createElement("div");
      row.className = "scoring-bucket";
      appendText(row, "span", "scoring-bucket-label", bucket.bucket || "");

      var track = document.createElement("div");
      track.className = "scoring-bucket-track";
      var applied = document.createElement("span");
      applied.className = "scoring-bucket-fill";
      applied.style.width = formatRate(bucket.application_rate || 0);
      track.appendChild(applied);
      row.appendChild(track);

      appendText(
        row,
        "span",
        "scoring-bucket-rate",
        formatRate(bucket.application_rate || 0) + " applied"
      );
      section.appendChild(row);
    });
    container.appendChild(section);
  }

  function renderMismatchList(container, title, rows) {
    var section = document.createElement("div");
    section.className = "scoring-section";
    appendText(section, "h4", null, title);

    if (!rows || !rows.length) {
      appendText(section, "p", "scoring-muted", "None");
      container.appendChild(section);
      return;
    }

    var list = document.createElement("ul");
    list.className = "scoring-list";
    rows.forEach(function (row) {
      var item = document.createElement("li");
      var titleText = (row.title || "Untitled") + " @ " + (row.company || "Unknown");
      appendText(item, "span", "scoring-job-title", titleText);
      appendText(
        item,
        "span",
        "scoring-job-meta",
        "Score " + String(row.fit_score) + " - " + (row.user_status || "unknown")
      );
      list.appendChild(item);
    });
    section.appendChild(list);
    container.appendChild(section);
  }

  function renderScoringPanel(panel, data) {
    var summary = data && data.summary ? data.summary : {};
    var mismatches = data && data.mismatches ? data.mismatches : {};
    clearRendered(panel);
    hideEmptyState(panel);

    var container = document.createElement("div");
    container.className = "scoring-content";
    container.setAttribute("data-analytics-rendered", "scoring");

    renderCounters(container, summary);
    renderBuckets(container, data && data.buckets ? data.buckets : []);
    renderMismatchList(
      container,
      "High score dismissed",
      mismatches.high_score_dismissed || []
    );
    renderMismatchList(
      container,
      "Low score pursued",
      mismatches.low_score_applied || []
    );
    renderMismatchList(container, "Pending review", mismatches.pending_review || []);

    panel.appendChild(container);
  }

  function hasContent(data) {
    if (!data || typeof data !== "object") return false;
    return Object.keys(data).some(function (key) {
      var value = data[key];
      if (Array.isArray(value)) return value.length > 0;
      if (value && typeof value === "object") return hasContent(value);
      return value !== null && value !== undefined && value !== "";
    });
  }

  function loadPanel(panel) {
    var endpoint = panel.getAttribute("data-analytics-endpoint");
    if (!endpoint || typeof fetch !== "function") {
      setStatus(panel, "Empty");
      renderEmptyState(panel, "No analytics data yet.");
      return;
    }

    fetch(endpoint, { headers: { "Accept": "application/json" } })
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then(function (data) {
        setStatus(panel, hasContent(data) ? "Ready" : "Empty");
        if (endpoint === "/api/analytics/scoring") {
          renderScoringPanel(panel, data);
        } else {
          renderEmptyState(panel, "No analytics data yet.");
        }
      })
      .catch(function () {
        setStatus(panel, "Unavailable");
        renderEmptyState(panel, "Analytics data is unavailable.");
      });
  }

  panels.forEach(loadPanel);
}());
