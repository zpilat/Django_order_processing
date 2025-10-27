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
      var kamionCell = row.querySelector("td.field-kamion_prijem_link");
      var currentKamionText = kamionCell ? kamionCell.textContent.trim() : "";
      var currentGroupKey = currentZakazkaText + "||" + currentKamionText;

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
