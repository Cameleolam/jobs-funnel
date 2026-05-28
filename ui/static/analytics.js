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
        renderEmptyState(panel, "No analytics data yet.");
      })
      .catch(function () {
        setStatus(panel, "Unavailable");
        renderEmptyState(panel, "Analytics data is unavailable.");
      });
  }

  panels.forEach(loadPanel);
}());
