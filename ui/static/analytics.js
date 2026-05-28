(function () {
  var panels = document.querySelectorAll("[data-analytics-endpoint]");
  if (!panels.length) return;
  var shell = document.querySelector(".analytics-shell");
  var viewButtons = document.querySelectorAll("[data-analytics-view-button]");
  var windowSelect = document.querySelector("[data-analytics-window]");
  var topicLimitSelect = document.querySelector("[data-analytics-topic-limit]");

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

  function renderInsightCards(container, cards) {
    var filtered = (cards || []).filter(function (card) {
      return card && card.value !== null && card.value !== undefined && card.value !== "";
    });
    if (!filtered.length) return;

    var section = document.createElement("div");
    section.className = "analytics-insights";
    filtered.forEach(function (card) {
      var item = document.createElement("div");
      item.className = "analytics-insight";
      appendText(item, "span", "analytics-insight-label", card.label || "");
      appendText(item, "span", "analytics-insight-value", String(card.value));
      if (card.detail) appendText(item, "span", "analytics-insight-detail", card.detail);
      section.appendChild(item);
    });
    container.appendChild(section);
  }

  function formatRate(value) {
    var number = Number(value);
    if (!Number.isFinite(number)) return "0%";
    return Math.round(number * 100) + "%";
  }

  function sumBy(items, key) {
    return (items || []).reduce(function (total, item) {
      return total + (Number(item[key]) || 0);
    }, 0);
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

  function renderScoringInsights(container, data) {
    var summary = data && data.summary ? data.summary : {};
    var mismatches = data && data.mismatches ? data.mismatches : {};
    var highDismissed = (mismatches.high_score_dismissed || []).length;
    var lowPursued = (mismatches.low_score_applied || []).length;
    var pending = (mismatches.pending_review || []).length;
    var bestBucket = (data && data.buckets ? data.buckets : []).reduce(function (best, bucket) {
      if (!best || Number(bucket.application_rate || 0) > Number(best.application_rate || 0)) {
        return bucket;
      }
      return best;
    }, null);

    renderInsightCards(container, [
      {
        label: "Mismatch load",
        value: highDismissed + lowPursued,
        detail: "high-score dismissed + low-score pursued",
      },
      {
        label: "Review queue",
        value: pending || summary.pending_review || 0,
        detail: "pending or human-review jobs",
      },
      bestBucket ? {
        label: "Best bucket",
        value: bestBucket.bucket,
        detail: formatRate(bestBucket.application_rate || 0) + " applied",
      } : null,
    ]);
  }

  function renderFunnelCounters(container, summary) {
    var counters = document.createElement("div");
    counters.className = "funnel-counters";
    [
      ["Tracked", "tracked_jobs"],
      ["Applied", "applied"],
      ["Open", "in_process"],
      ["Rejected", "rejected"],
      ["Closed", "closed"],
      ["Interviews", "interviews"],
    ].forEach(function (item) {
      var counter = document.createElement("div");
      counter.className = "funnel-counter";
      appendText(counter, "span", "funnel-counter-value", String(summary[item[1]] || 0));
      appendText(counter, "span", "funnel-counter-label", item[0]);
      counters.appendChild(counter);
    });
    var closeText = summary.avg_days_to_close === null || summary.avg_days_to_close === undefined
      ? "n/a"
      : String(summary.avg_days_to_close);
    var closeCounter = document.createElement("div");
    closeCounter.className = "funnel-counter";
    appendText(closeCounter, "span", "funnel-counter-value", closeText);
    appendText(closeCounter, "span", "funnel-counter-label", "Avg days close");
    counters.appendChild(closeCounter);
    container.appendChild(counters);
  }

  function renderFunnelLegend(section) {
    var legend = document.createElement("div");
    legend.className = "funnel-legend";
    [
      ["application", "Application"],
      ["contact", "Contact"],
      ["interview", "Interview"],
      ["task", "Task"],
      ["decision", "Decision"],
      ["note", "Note"],
    ].forEach(function (item) {
      var label = document.createElement("span");
      label.className = "funnel-legend-item";
      var swatch = document.createElement("span");
      swatch.className = "funnel-legend-swatch funnel-week-fill-" + item[0];
      label.appendChild(swatch);
      appendText(label, "span", null, item[1]);
      legend.appendChild(label);
    });
    section.appendChild(legend);
  }

  function renderFunnelTimeline(container, weeks) {
    var section = document.createElement("div");
    section.className = "funnel-section";
    appendText(section, "h4", null, "Weekly events");
    renderFunnelLegend(section);

    if (!weeks || !weeks.length) {
      appendText(section, "p", "scoring-muted", "No events in this window.");
      container.appendChild(section);
      return;
    }

    var maxTotal = weeks.reduce(function (max, week) {
      return Math.max(max, Number(week.total) || 0);
    }, 1);
    var timeline = document.createElement("div");
    timeline.className = "funnel-timeline";
    weeks.forEach(function (week) {
      var row = document.createElement("div");
      row.className = "funnel-week";
      appendText(row, "span", "funnel-week-label", String(week.week || ""));

      var track = document.createElement("div");
      track.className = "funnel-week-track";
      ["application", "contact", "interview", "task", "decision", "note"].forEach(function (kind) {
        var count = Number(week[kind]) || 0;
        if (!count) return;
        var fill = document.createElement("span");
        fill.className = "funnel-week-fill funnel-week-fill-" + kind;
        fill.style.width = Math.max(4, Math.round((count / maxTotal) * 100)) + "%";
        fill.title = kind + ": " + count;
        track.appendChild(fill);
      });
      row.appendChild(track);
      appendText(row, "span", "funnel-week-total", String(week.total || 0));
      timeline.appendChild(row);
    });
    section.appendChild(timeline);
    container.appendChild(section);
  }

  function renderFunnelInsights(container, data) {
    var summary = data && data.summary ? data.summary : {};
    var weeks = data && data.weeks ? data.weeks : [];
    var stuck = data && data.stuck_jobs ? data.stuck_jobs : [];
    var busiest = weeks.reduce(function (best, week) {
      return !best || Number(week.total || 0) > Number(best.total || 0) ? week : best;
    }, null);
    var applications = sumBy(weeks, "application");
    var interviews = Number(summary.interviews) || 0;
    var ratio = applications > 0 ? Math.round((interviews / applications) * 100) + "%" : "n/a";

    renderInsightCards(container, [
      {
        label: "Stuck jobs",
        value: stuck.length,
        detail: "tracked with no recent event",
      },
      busiest ? {
        label: "Busiest week",
        value: String(busiest.week || ""),
        detail: String(busiest.total || 0) + " events",
      } : null,
      {
        label: "Interview ratio",
        value: ratio,
        detail: "interviews / weekly applications",
      },
    ]);
  }

  function renderStuckJobs(container, jobs) {
    var section = document.createElement("div");
    section.className = "funnel-section";
    appendText(section, "h4", null, "Stuck jobs");

    if (!jobs || !jobs.length) {
      appendText(section, "p", "scoring-muted", "None");
      container.appendChild(section);
      return;
    }

    var list = document.createElement("ul");
    list.className = "funnel-stuck-list";
    jobs.forEach(function (job) {
      var item = document.createElement("li");
      var titleText = (job.title || "Untitled") + " @ " + (job.company || "Unknown");
      appendText(item, "span", "scoring-job-title", titleText);
      appendText(
        item,
        "span",
        "scoring-job-meta",
        (job.user_status || "unknown") + " - " + String(job.days_since_last_event || 0) + " days"
      );
      list.appendChild(item);
    });
    section.appendChild(list);
    container.appendChild(section);
  }

  function renderMarketCounters(container, summary) {
    var counters = document.createElement("div");
    counters.className = "market-counters";
    [
      ["Jobs", "total_jobs"],
      ["Topics", "topic_count"],
      ["Fit signals", "signal_jobs"],
    ].forEach(function (item) {
      var counter = document.createElement("div");
      counter.className = "market-counter";
      appendText(counter, "span", "market-counter-value", String(summary[item[1]] || 0));
      appendText(counter, "span", "market-counter-label", item[0]);
      counters.appendChild(counter);
    });
    container.appendChild(counters);
  }

  function shortWeekLabel(week) {
    var text = String(week || "");
    return text.length >= 10 ? text.slice(5, 10) : text;
  }

  function renderMarketHeatmap(container, data) {
    var topics = data && data.topics ? data.topics : [];
    var weeks = data && data.weeks ? data.weeks : [];
    var section = document.createElement("div");
    section.className = "market-section";
    appendText(section, "h4", null, "Weekly topics by publish date");

    if (!topics.length || !weeks.length) {
      appendText(section, "p", "scoring-muted", "No market topics in this window.");
      container.appendChild(section);
      return;
    }

    var maxCount = topics.reduce(function (max, topic) {
      return Math.max(max, Number(topic.total) || 0);
    }, 1);
    var table = document.createElement("div");
    table.className = "market-heatmap";
    table.style.gridTemplateColumns = "minmax(82px, 1fr) repeat(" + weeks.length + ", 34px)";
    appendText(table, "span", "market-heatmap-heading", "Topic");
    weeks.forEach(function (week) {
      appendText(table, "span", "market-heatmap-week", shortWeekLabel(week));
    });

    topics.forEach(function (topic) {
      var label = appendText(table, "span", "market-topic-label", topic.topic || "");
      label.title = String(topic.total || 0) + " jobs, " + String(topic.signal_total || 0) + " signals";
      (topic.weeks || []).forEach(function (week) {
        var count = Number(week.count) || 0;
        var signalCount = Number(week.signal_count) || 0;
        var cell = appendText(table, "span", "market-cell", String(count));
        cell.title = String(topic.topic || "") + " " + String(week.week || "") + ": "
          + count + " jobs, " + signalCount + " signals";
        cell.setAttribute("data-signal-count", String(signalCount));
        cell.style.opacity = String(0.35 + (0.65 * (count / maxCount)));
      });
    });
    section.appendChild(table);
    container.appendChild(section);
  }

  function marketInsight(topic, value, detail) {
    if (!topic) return null;
    return {
      label: value,
      value: topic.topic,
      detail: detail(topic),
    };
  }

  function renderMarketInsights(container, data) {
    var insights = data && data.insights ? data.insights : {};
    var summary = data && data.summary ? data.summary : {};
    var basis = summary.date_basis || {};
    renderInsightCards(container, [
      marketInsight(
        (insights.rising_topics || [])[0],
        "Rising",
        function (topic) { return "+" + topic.delta + " jobs vs previous week"; }
      ),
      marketInsight(
        (insights.fading_topics || [])[0],
        "Fading",
        function (topic) { return String(topic.delta) + " jobs vs previous week"; }
      ),
      marketInsight(
        (insights.high_signal_topics || [])[0],
        "High-fit topic",
        function (topic) { return formatRate(topic.signal_rate || 0) + " PASS/MAYBE"; }
      ),
      marketInsight(
        (insights.noisy_topics || [])[0],
        "Noisy topic",
        function (topic) { return String(topic.total || 0) + " jobs, " + formatRate(topic.signal_rate || 0) + " fit"; }
      ),
      {
        label: "Date basis",
        value: String(basis.posted_at || 0) + " posted",
        detail: String(basis.crawled_at || 0) + " crawled fallback, "
          + String(basis.analyzed_at || 0) + " analyzed fallback",
      },
    ]);
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
    renderScoringInsights(container, data || {});
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

  function renderMarketPanel(panel, data) {
    var summary = data && data.summary ? data.summary : {};
    clearRendered(panel);
    hideEmptyState(panel);

    var container = document.createElement("div");
    container.className = "market-content";
    container.setAttribute("data-analytics-rendered", "market");

    renderMarketCounters(container, summary);
    renderMarketInsights(container, data || {});
    renderMarketHeatmap(container, data || {});

    panel.appendChild(container);
  }

  function renderFunnelPanel(panel, data) {
    var summary = data && data.summary ? data.summary : {};
    clearRendered(panel);
    hideEmptyState(panel);

    var container = document.createElement("div");
    container.className = "funnel-content";
    container.setAttribute("data-analytics-rendered", "funnel");

    renderFunnelCounters(container, summary);
    renderFunnelInsights(container, data || {});
    renderFunnelTimeline(container, data && data.weeks ? data.weeks : []);
    renderStuckJobs(container, data && data.stuck_jobs ? data.stuck_jobs : []);

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

  function selectedValue(element, fallback) {
    return element && element.value ? element.value : fallback;
  }

  function buildEndpoint(panel) {
    var endpoint = panel.getAttribute("data-analytics-endpoint");
    if (!endpoint) return "";
    if (endpoint.indexOf("/api/analytics/funnel") === 0) {
      return endpoint + "?weeks=" + encodeURIComponent(selectedValue(windowSelect, "12"));
    }
    if (endpoint.indexOf("/api/analytics/market-shifts") === 0) {
      return endpoint + "?weeks=" + encodeURIComponent(selectedValue(windowSelect, "12"))
        + "&limit=" + encodeURIComponent(selectedValue(topicLimitSelect, "20"));
    }
    return endpoint;
  }

  function setPanelLoading(panel) {
    setStatus(panel, "Loading");
    clearRendered(panel);
    renderEmptyState(panel, "Loading analytics.");
  }

  function reloadPanels() {
    panels.forEach(function (panel) {
      setPanelLoading(panel);
      loadPanel(panel);
    });
  }

  function setView(view) {
    var normalized = view || "all";
    if (shell) {
      shell.setAttribute("data-analytics-view", normalized);
      ["all", "scoring", "funnel", "market"].forEach(function (option) {
        shell.classList.toggle("view-" + option, option === normalized);
      });
    }
    viewButtons.forEach(function (button) {
      button.classList.toggle("active", button.getAttribute("data-analytics-view-button") === normalized);
    });
  }

  function loadPanel(panel) {
    var endpoint = buildEndpoint(panel);
    var baseEndpoint = panel.getAttribute("data-analytics-endpoint") || "";
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
        if (baseEndpoint === "/api/analytics/scoring") {
          renderScoringPanel(panel, data);
        } else if (baseEndpoint.indexOf("/api/analytics/funnel") === 0) {
          renderFunnelPanel(panel, data);
        } else if (baseEndpoint.indexOf("/api/analytics/market-shifts") === 0) {
          renderMarketPanel(panel, data);
        } else {
          renderEmptyState(panel, "No analytics data yet.");
        }
      })
      .catch(function () {
        setStatus(panel, "Unavailable");
        renderEmptyState(panel, "Analytics data is unavailable.");
      });
  }

  viewButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      setView(button.getAttribute("data-analytics-view-button"));
    });
  });
  if (windowSelect) windowSelect.addEventListener("change", reloadPanels);
  if (topicLimitSelect) topicLimitSelect.addEventListener("change", reloadPanels);
  setView(shell ? shell.getAttribute("data-analytics-view") : "all");
  panels.forEach(loadPanel);
}());
