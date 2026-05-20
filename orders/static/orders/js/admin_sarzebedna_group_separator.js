(function () {
  "use strict";

  function initGroupSeparators() {
    var body = document.body;
    if (!body) {
      return;
    }

    var isSarzeKrokBednaChangeList = body.classList.contains("app-orders") &&
      body.classList.contains("change-list") &&
      (
        body.classList.contains("model-sarzekrokbedna") ||
        body.classList.contains("model-sarzebedna")
      );

    if (!isSarzeKrokBednaChangeList && !document.querySelector("#result_list .field-get_krok")) {
      return;
    }

    var rows = document.querySelectorAll("#result_list tbody tr");
    if (!rows.length) {
      return;
    }

    var lastGroupKey = null;
    rows.forEach(function (row, index) {
      var krokCell = row.querySelector("td.field-get_krok");
      if (!krokCell) {
        return;
      }

      var krokLink = krokCell.querySelector('a[href*="/admin/orders/sarzekrok/"]');
      var href = krokLink ? krokLink.getAttribute("href") || "" : "";
      var idMatch = href.match(/\/admin\/orders\/sarzekrok\/(\d+)\//);
      var currentGroupKey = idMatch ? idMatch[1] : (krokLink ? krokLink.textContent.trim() : krokCell.textContent.trim());

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
