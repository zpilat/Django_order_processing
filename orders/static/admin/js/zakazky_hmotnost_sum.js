document.addEventListener('DOMContentLoaded', function() {
    // Box zobrazuj jen, pokud je ve stránce tabulka s id 'result_list'
    const resultsTable = document.getElementById('result_list');
    if (!resultsTable) return;

    function updateSum() {
        let sum = 0;
        document.querySelectorAll('input.action-select:checked').forEach(function(checkbox) {
            const row = checkbox.closest('tr');
            const hmotnostCell = row.querySelector('td.field-hmotnost_zakazky');
            if (hmotnostCell) {
                let val = parseFloat(hmotnostCell.textContent.replace(',', '.'));
                if (!isNaN(val)) sum += val;
            }
        });
        let box = document.getElementById('hmotnost-sum-box');
        if (!box) {
            box = document.createElement('div');
            box.id = 'hmotnost-sum-box';
            box.className = 'alert alert-info shadow-sm';
            // Přidej box těsně před tabulku!
            resultsTable.parentNode.insertBefore(box, resultsTable);
            // Box je nyní v normálním toku stránky
            box.style = 'margin-bottom: 1em; font-size:1rem;font-family:inherit;';
        } else {
            box.className = 'alert alert-info shadow-sm';
        }
        box.innerHTML = `<i class="fas fa-balance-scale" style="margin-right:0.5em;color:#0174c6;"></i> Hmotnost označených zakázek:<strong><span style="margin-left:0.5em;">${sum.toFixed(1)} kg</span></strong>`;
    }

    document.querySelectorAll('input.action-select').forEach(function(checkbox) {
        checkbox.addEventListener('change', updateSum);
    });

    let selectAll = document.getElementById('action-toggle');
    if (selectAll) {
        selectAll.addEventListener('change', updateSum);
    }

    updateSum();
});
