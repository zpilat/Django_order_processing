document.addEventListener('DOMContentLoaded', function() {
    // Box zobrazuj jen, pokud je na stránce tabulka s id 'result_list'
    const resultsTable = document.getElementById('result_list');
    if (!resultsTable) return;

    function updateSummary() {
        let weightSum = 0;
        let boxCountSum = 0;

        document.querySelectorAll('input.action-select:checked').forEach(function(checkbox) {
            const row = checkbox.closest('tr');

            // Brutto hmotnost
            const hmotnostCell = row.querySelector('td.field-hmotnost_zakazky_k_expedici_brutto');
            if (hmotnostCell) {
                let val = parseFloat(hmotnostCell.textContent.replace(',', '.'));
                if (!isNaN(val)) weightSum += val;
            }

            // Počet beden
            const pocetCell = row.querySelector('td.field-pocet_beden_k_expedici');
            if (pocetCell) {
                let cnt = parseInt(pocetCell.textContent, 10);
                if (!isNaN(cnt)) boxCountSum += cnt;
            }
        });

        let box = document.getElementById('hmotnost-summary');
        if (!box) {
            box = document.createElement('div');
            box.id = 'hmotnost-summary';
            // místo <ul class="messagelist"> použijeme čistý <div> s admin-class 'info'
            box.className = 'info';
            // vložíme před tabulku
            resultsTable.parentNode.insertBefore(box, resultsTable);
            // styl pro admin-info
            box.style.marginBottom = '1em';
            box.style.padding = '0.5em';
            box.style.backgroundColor = '#f8f9fa';  // světle šedá
            box.style.fontSize = '0.8rem';
            box.style.fontFamily = 'inherit';
        }

        // jednorádkový obsah
        box.innerHTML = `
            <i class="fas fa-boxes" style="margin-right:0.5em;"></i>
            Celkový počet beden v označených zakázkách: <strong>${boxCountSum}</strong>        
            &nbsp;|&nbsp;
            <i class="fas fa-balance-scale" style="margin-right:0.5em;"></i>
            Celková brutto hmotnost beden k expedici v označených zakázkách: <strong>${weightSum.toFixed(1)} kg</strong>
        `;
    }

    document.querySelectorAll('input.action-select').forEach(function(checkbox) {
        checkbox.addEventListener('change', updateSummary);
    });
    const selectAll = document.getElementById('action-toggle');
    if (selectAll) selectAll.addEventListener('change', updateSummary);

    updateSummary();
});
