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

  function renderFunnelTimeline(container, weeks) {
    var section = document.createElement("div");
    section.className = "funnel-section";
    appendText(section, "h4", null, "Weekly events");

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
      ["Signals", "signal_jobs"],
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
    appendText(section, "h4", null, "Weekly topics");

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

  function renderMarketPanel(panel, data) {
    var summary = data && data.summary ? data.summary : {};
    clearRendered(panel);
    hideEmptyState(panel);

    var container = document.createElement("div");
    container.className = "market-content";
    container.setAttribute("data-analytics-rendered", "market");

    renderMarketCounters(container, summary);
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
        } else if (endpoint.indexOf("/api/analytics/funnel") === 0) {
          renderFunnelPanel(panel, data);
        } else if (endpoint.indexOf("/api/analytics/market-shifts") === 0) {
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

  panels.forEach(loadPanel);
}());
