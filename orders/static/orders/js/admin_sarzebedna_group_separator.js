(function () {
  "use strict";

  function initGroupSeparators() {
    var body = document.body;
    if (!body) {
      return;
    }

    var isSarzeBednaChangeList = body.classList.contains("app-orders") &&
      body.classList.contains("change-list") &&
      body.classList.contains("model-sarzebedna");

    if (!isSarzeBednaChangeList && !document.querySelector("#result_list .field-get_sarze")) {
      return;
    }

    var rows = document.querySelectorAll("#result_list tbody tr");
    if (!rows.length) {
      return;
    }

    var lastGroupKey = null;
    rows.forEach(function (row, index) {
      var sarzeCell = row.querySelector("td.field-get_sarze");
      if (!sarzeCell) {
        return;
      }

      var sarzeLink = sarzeCell.querySelector('a[href*="/admin/orders/sarze/"]');
      var sarzeKey = sarzeLink ? sarzeLink.textContent.trim() : sarzeCell.textContent.trim();
      var currentGroupKey = sarzeKey;

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
