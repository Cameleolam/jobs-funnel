(function () {
  var panels = document.querySelectorAll("[data-insights-panel]");
  if (!panels.length) return;

  var shell = document.querySelector(".analytics-shell");
  var viewButtons = document.querySelectorAll("[data-analytics-view-button]");
  var marketWindowSelect = document.querySelector("[data-market-window]");
  var marketTopicLimitSelect = document.querySelector("[data-market-topic-limit]");
  var marketDateModeSelect = document.querySelector("[data-market-date-mode]");
  var state = { scoring: null, funnel: null, market: null };

  function panelFor(name) {
    return document.querySelector('[data-insights-panel="' + name + '"]');
  }

  function setStatus(panel, text) {
    var status = panel ? panel.querySelector("[data-analytics-status]") : null;
    if (status) status.textContent = text;
  }

  function renderEmptyState(panel, message) {
    var empty = panel ? panel.querySelector("[data-analytics-empty]") : null;
    if (!empty) return;
    empty.textContent = message;
    empty.hidden = false;
  }

  function hideEmptyState(panel) {
    var empty = panel ? panel.querySelector("[data-analytics-empty]") : null;
    if (empty) empty.hidden = true;
  }

  function clearRendered(panel) {
    if (!panel) return;
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

  function selectedValue(element, fallback) {
    return element && element.value ? element.value : fallback;
  }

  function list(value) {
    return Array.isArray(value) ? value : [];
  }

  function jobHref(job) {
    if (job && job.job_url) return job.job_url;
    if (job && job.id !== null && job.id !== undefined) return "/jobs/" + encodeURIComponent(job.id) + "/view";
    return "#";
  }

  function renderInsightCards(container, cards) {
    var filtered = list(cards).filter(function (card) {
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

  function renderJobList(container, title, jobs, emptyText, metaFn) {
    var section = document.createElement("div");
    section.className = "insights-section";
    appendText(section, "h4", null, title);

    if (!jobs || !jobs.length) {
      appendText(section, "p", "analytics-muted", emptyText || "None");
      container.appendChild(section);
      return;
    }

    var rows = document.createElement("ul");
    rows.className = "insights-job-list";
    jobs.forEach(function (job) {
      var item = document.createElement("li");
      var link = document.createElement("a");
      link.className = "insights-job-link";
      link.href = jobHref(job);
      link.textContent = (job.title || "Untitled") + " @ " + (job.company || "Unknown");
      item.appendChild(link);
      appendText(
        item,
        "span",
        "insights-job-meta",
        metaFn ? metaFn(job) : "Score " + String(job.fit_score || "?")
      );
      rows.appendChild(item);
    });
    section.appendChild(rows);
    container.appendChild(section);
  }

  function renderPanel(panel, name, renderFn) {
    clearRendered(panel);
    hideEmptyState(panel);
    var container = document.createElement("div");
    container.className = "insights-content";
    container.setAttribute("data-analytics-rendered", name);
    renderFn(container);
    panel.appendChild(container);
    setStatus(panel, "Ready");
  }

  function renderActPanel(panel, scoring, funnel) {
    var actionQueue = scoring && scoring.action_queue ? scoring.action_queue : {};
    var applyTargets = list(actionQueue.apply_targets);
    var reviewCandidates = list(actionQueue.review_candidates);
    var stuckJobs = list(funnel && funnel.stuck_jobs);

    renderPanel(panel, "act", function (container) {
      renderInsightCards(container, [
        { label: "Apply targets", value: applyTargets.length, detail: "high-fit jobs with no status" },
        { label: "Review candidates", value: reviewCandidates.length, detail: "score 4-6 with no status" },
        { label: "Follow-ups", value: stuckJobs.length, detail: "tracked jobs with no recent event" },
      ]);
      renderJobList(container, "Apply targets", applyTargets, "No high-fit unacted jobs.", function (job) {
        return "Score " + String(job.fit_score || "?") + " - " + (job.decision || "unknown");
      });
      renderJobList(container, "Review candidates", reviewCandidates, "No review-band unacted jobs.", function (job) {
        return "Score " + String(job.fit_score || "?") + " - needs decision";
      });
      renderJobList(container, "Follow-ups", stuckJobs, "No stuck tracked jobs.", function (job) {
        return (job.user_status || "tracked") + " - " + String(job.days_since_last_event || 0) + " days";
      });
    });
  }

  function renderLearnPanel(panel, scoring) {
    var mismatches = scoring && scoring.mismatches ? scoring.mismatches : {};
    var highDismissed = list(mismatches.high_score_dismissed);
    var lowPursued = list(mismatches.low_score_applied);
    var pendingReview = list(mismatches.pending_review);

    renderPanel(panel, "learn", function (container) {
      renderInsightCards(container, [
        { label: "High-score dismissed", value: highDismissed.length, detail: "possible scorer false positives" },
        { label: "Low-score pursued", value: lowPursued.length, detail: "possible scorer false negatives" },
        { label: "Pending review", value: pendingReview.length, detail: "needs calibration decision" },
      ]);
      renderJobList(container, "High-score dismissed", highDismissed, "None.", function (job) {
        return "Score " + String(job.fit_score || "?") + " - dismissed";
      });
      renderJobList(container, "Low-score pursued", lowPursued, "None.", function (job) {
        return "Score " + String(job.fit_score || "?") + " - " + (job.user_status || "pursued");
      });
      renderJobList(container, "Pending review", pendingReview, "None.", function (job) {
        return "Score " + String(job.fit_score || "?") + " - resolve review";
      });
    });
  }

  function renderSourceQuality(container, sources) {
    var section = document.createElement("div");
    section.className = "insights-section";
    appendText(section, "h4", null, "Source quality");

    if (!sources || !sources.length) {
      appendText(section, "p", "analytics-muted", "No source quality data.");
      container.appendChild(section);
      return;
    }

    var rows = document.createElement("div");
    rows.className = "source-quality-list";
    sources.slice(0, 8).forEach(function (source) {
      var row = document.createElement("div");
      row.className = "source-quality-row";
      appendText(row, "span", "source-quality-name", source.source || "unknown");
      appendText(
        row,
        "span",
        "source-quality-meta",
        String(source.high_score || 0) + " high / " + String(source.total || 0)
          + " jobs - " + formatRate(source.high_score_rate || 0)
      );
      rows.appendChild(row);
    });
    section.appendChild(rows);
    container.appendChild(section);
  }

  function renderFunnelTimeline(container, weeks) {
    var eventKinds = [
      ["application", "Application"],
      ["contact", "Contact"],
      ["interview", "Interview"],
      ["task", "Task"],
      ["outcome", "Outcome"],
      ["note", "Note"],
    ];
    var section = document.createElement("div");
    section.className = "insights-section";
    appendText(section, "h4", null, "Weekly funnel events");

    if (!weeks || !weeks.length) {
      appendText(section, "p", "analytics-muted", "No events in this window.");
      container.appendChild(section);
      return;
    }

    var legend = document.createElement("div");
    legend.className = "funnel-legend";
    eventKinds.forEach(function (item) {
      var label = document.createElement("span");
      label.className = "funnel-legend-item";
      var swatch = document.createElement("span");
      swatch.className = "funnel-legend-swatch funnel-week-fill-" + item[0];
      label.appendChild(swatch);
      appendText(label, "span", null, item[1]);
      legend.appendChild(label);
    });
    section.appendChild(legend);

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
      eventKinds.forEach(function (item) {
        var kind = item[0];
        var count = Number(week[kind]) || 0;
        if (!count) return;
        var fill = document.createElement("span");
        fill.className = "funnel-week-fill funnel-week-fill-" + kind;
        fill.style.width = Math.max(4, Math.round((count / maxTotal) * 100)) + "%";
        fill.title = item[1] + ": " + count;
        track.appendChild(fill);
      });
      row.appendChild(track);

      var detail = String(week.total || 0);
      if (Number(week.review_decision) > 0) {
        detail += " +" + String(week.review_decision) + "r";
      }
      appendText(row, "span", "funnel-week-total", detail);
      timeline.appendChild(row);
    });
    section.appendChild(timeline);
    container.appendChild(section);
  }

  function renderImprovePanel(panel, scoring, funnel) {
    var summary = funnel && funnel.summary ? funnel.summary : {};
    var sources = list(scoring && scoring.source_quality);

    renderPanel(panel, "improve", function (container) {
      renderInsightCards(container, [
        { label: "Applied", value: summary.applied || 0, detail: "tracked or status-applied jobs" },
        { label: "Interviews", value: summary.interviews || 0, detail: "recorded interview events" },
        {
          label: "Avg close",
          value: summary.avg_days_to_close === null || summary.avg_days_to_close === undefined
            ? "n/a"
            : String(summary.avg_days_to_close) + "d",
          detail: "application to closed",
        },
      ]);
      renderSourceQuality(container, sources);
      renderFunnelTimeline(container, list(funnel && funnel.weeks));
    });
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
    var topics = list(data && data.topics);
    var weeks = list(data && data.weeks);
    var section = document.createElement("div");
    section.className = "market-section";
    appendText(section, "h4", null, "Weekly topics");

    if (!topics.length || !weeks.length) {
      appendText(section, "p", "analytics-muted", "No market topics in this window.");
      container.appendChild(section);
      return;
    }

    var maxCount = topics.reduce(function (max, topic) {
      return Math.max(max, Number(topic.total) || 0);
    }, 1);
    var table = document.createElement("div");
    table.className = "market-heatmap";
    table.style.gridTemplateColumns = "minmax(96px, 1fr) repeat(" + weeks.length + ", 34px)";
    appendText(table, "span", "market-heatmap-heading", "Topic");
    weeks.forEach(function (week) {
      appendText(table, "span", "market-heatmap-week", shortWeekLabel(week));
    });

    topics.forEach(function (topic) {
      var label = appendText(table, "span", "market-topic-label", topic.topic || "");
      label.title = String(topic.total || 0) + " jobs, " + String(topic.signal_total || 0) + " signals";
      list(topic.weeks).forEach(function (week) {
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
    return { label: value, value: topic.topic, detail: detail(topic) };
  }

  function renderMarketInsights(container, data) {
    var insights = data && data.insights ? data.insights : {};
    var summary = data && data.summary ? data.summary : {};
    var basis = summary.date_basis || {};
    var fallbackCount = Number(basis.crawled_at || 0) + Number(basis.analyzed_at || 0);
    var totalJobs = Number(summary.total_jobs || 0);
    var signalJobs = Number(summary.signal_jobs || 0);

    renderInsightCards(container, [
      marketInsight(
        list(insights.high_signal_topics)[0],
        "High-fit topic",
        function (topic) { return formatRate(topic.signal_rate || 0) + " PASS/MAYBE"; }
      ),
      marketInsight(
        list(insights.noisy_topics)[0],
        "Noisy topic",
        function (topic) { return String(topic.total || 0) + " jobs, " + formatRate(topic.signal_rate || 0) + " fit"; }
      ),
      marketInsight(
        list(insights.fading_topics).find(function (topic) {
          return Number(topic.signal_total || 0) > 0;
        }),
        "Cooling signal",
        function (topic) { return String(topic.delta || 0) + " jobs vs previous week"; }
      ),
      {
        label: "Signal density",
        value: totalJobs ? formatRate(signalJobs / totalJobs) : "0%",
        detail: String(signalJobs) + " fit signals in this window",
      },
      {
        label: "Date basis",
        value: summary.date_mode === "fallback" ? "Fallback included" : "Posted only",
        detail: String(basis.posted_at || 0) + " posted, " + String(fallbackCount) + " fallback",
      },
    ]);
  }

  function renderMarketPanel(panel, data) {
    var summary = data && data.summary ? data.summary : {};
    renderPanel(panel, "market", function (container) {
      renderMarketCounters(container, summary);
      renderMarketInsights(container, data || {});
      renderMarketHeatmap(container, data || {});
    });
  }

  function setPanelLoading(panel, text) {
    setStatus(panel, "Loading");
    clearRendered(panel);
    renderEmptyState(panel, text || "Loading insights.");
  }

  function fetchJson(url) {
    return fetch(url, { headers: { "Accept": "application/json" } }).then(function (response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    });
  }

  function loadCore() {
    ["act", "learn", "improve"].forEach(function (name) {
      setPanelLoading(panelFor(name), "Loading insights.");
    });

    Promise.all([
      fetchJson("/api/analytics/scoring"),
      fetchJson("/api/analytics/funnel?weeks=12"),
    ]).then(function (results) {
      state.scoring = results[0];
      state.funnel = results[1];
      renderActPanel(panelFor("act"), state.scoring, state.funnel);
      renderLearnPanel(panelFor("learn"), state.scoring);
      renderImprovePanel(panelFor("improve"), state.scoring, state.funnel);
    }).catch(function () {
      ["act", "learn", "improve"].forEach(function (name) {
        var panel = panelFor(name);
        setStatus(panel, "Unavailable");
        renderEmptyState(panel, "Insights data is unavailable.");
      });
    });
  }

  function marketEndpoint() {
    return "/api/analytics/market-shifts?weeks=" + encodeURIComponent(selectedValue(marketWindowSelect, "12"))
      + "&limit=" + encodeURIComponent(selectedValue(marketTopicLimitSelect, "20"))
      + "&date_mode=" + encodeURIComponent(selectedValue(marketDateModeSelect, "posted"));
  }

  function loadMarket() {
    var panel = panelFor("market");
    setPanelLoading(panel, "Loading market signals.");
    fetchJson(marketEndpoint()).then(function (data) {
      state.market = data;
      renderMarketPanel(panel, state.market);
    }).catch(function () {
      setStatus(panel, "Unavailable");
      renderEmptyState(panel, "Market data is unavailable.");
    });
  }

  function setView(view) {
    var normalized = view || "all";
    if (shell) {
      shell.setAttribute("data-analytics-view", normalized);
      ["all", "act", "learn", "improve", "market"].forEach(function (option) {
        shell.classList.toggle("view-" + option, option === normalized);
      });
    }
    viewButtons.forEach(function (button) {
      button.classList.toggle("active", button.getAttribute("data-analytics-view-button") === normalized);
    });
  }

  viewButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      setView(button.getAttribute("data-analytics-view-button"));
    });
  });
  [marketWindowSelect, marketTopicLimitSelect, marketDateModeSelect].forEach(function (element) {
    if (element) element.addEventListener("change", loadMarket);
  });

  setView(shell ? shell.getAttribute("data-analytics-view") : "all");
  if (typeof fetch === "function") {
    loadCore();
    loadMarket();
  }
}());
