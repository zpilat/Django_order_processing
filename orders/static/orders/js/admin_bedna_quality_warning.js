(function () {
  "use strict";

  function initQualityWarnings() {
    document.querySelectorAll("#result_list [data-kontrola-neshoda]").forEach(function (marker) {
      var row = marker.closest("tr");
      var cell = row && row.querySelector("td.field-stav_bedny");
      if (!cell || cell.querySelector(".bedna-quality-warning")) {
        return;
      }

      cell.classList.add("bedna-quality-warning-cell");
      var warning = document.createElement("span");
      warning.className = "bedna-quality-warning";
      warning.title = "Neshoda při kontrole";
      cell.title = warning.title;
      warning.setAttribute("aria-label", warning.title);
      warning.setAttribute("role", "img");
      warning.textContent = "⚠\uFE0E";
      cell.insertBefore(warning, cell.firstChild);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initQualityWarnings);
  } else {
    initQualityWarnings();
  }
})();
