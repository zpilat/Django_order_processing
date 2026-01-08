(function () {
  "use strict";

  function initGroupSeparators() {
    var body = document.body;
    if (!body) {
      return;
    }

    var isBednaChangeList = body.classList.contains("app-orders") &&
      body.classList.contains("model-bedna") &&
      body.classList.contains("change-list");

    if (!isBednaChangeList) {
      return;
    }

    var rows = document.querySelectorAll("#result_list tbody tr");
    if (!rows.length) {
      return;
    }

    var lastGroupKey = null;
    rows.forEach(function (row, index) {
      var zakazkaCell = row.querySelector("td.field-zakazka_link");
      if (!zakazkaCell) {
        return;
      }

      var currentZakazkaText = zakazkaCell.textContent.trim();
      var zakazkaLink = zakazkaCell.querySelector("a");
      var zakazkaHref = zakazkaLink ? zakazkaLink.getAttribute("href") : "";
      var zakazkaIdMatch = zakazkaHref.match(/\/([0-9]+)\/change\/?$/);
      var zakazkaKey = zakazkaIdMatch ? zakazkaIdMatch[1] : currentZakazkaText;
      var currentGroupKey = zakazkaKey;

      if (index === 0) {
        lastGroupKey = currentGroupKey;
        return;
      }

      if (currentGroupKey !== lastGroupKey) {
        row.classList.add("bedna-group-separator");
        lastGroupKey = currentGroupKey;
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initGroupSeparators);
  } else {
    initGroupSeparators();
  }
})();
