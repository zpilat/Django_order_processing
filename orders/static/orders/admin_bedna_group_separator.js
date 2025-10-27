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

    var lastZakazkaText = null;
    rows.forEach(function (row, index) {
      var zakazkaCell = row.querySelector("td.field-zakazka_link");
      if (!zakazkaCell) {
        return;
      }

      var currentZakazkaText = zakazkaCell.textContent.trim();

      if (index === 0) {
        lastZakazkaText = currentZakazkaText;
        return;
      }

      if (currentZakazkaText !== lastZakazkaText) {
        row.classList.add("bedna-group-separator");
        lastZakazkaText = currentZakazkaText;
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initGroupSeparators);
  } else {
    initGroupSeparators();
  }
})();
