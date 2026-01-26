document.addEventListener('DOMContentLoaded', function() {
    // Box zobrazuj jen, pokud je na stránce tabulka s id 'result_list'
    const resultsTable = document.getElementById('result_list');
    if (!resultsTable) return;

    const darkQuery = window.matchMedia('(prefers-color-scheme: dark)');

    const themeAttr = () => (document.documentElement.dataset.theme || document.body.dataset.theme || '').toLowerCase();
    const isDark = () => {
        const t = themeAttr();
        if (t === 'light') return false;
        if (t === 'dark') return true;
        return darkQuery.matches
            || document.documentElement.classList.contains('dark')
            || document.body.classList.contains('dark');
    };

    function watchTheme(box) {
        const observer = new MutationObserver(() => applyTheme(box));
        observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'data-theme'] });
        observer.observe(document.body, { attributes: true, attributeFilter: ['class', 'data-theme'] });
        darkQuery.addEventListener('change', () => applyTheme(box));
    }

    function applyTheme(box) {
        if (isDark()) {
            box.style.setProperty('background-color', '#1f2937', 'important');
            box.style.setProperty('background', '#1f2937', 'important');
            box.style.setProperty('color', '#e5e7eb', 'important');
            box.style.setProperty('border', '1px solid #374151', 'important');
        } else {
            box.style.setProperty('background-color', '#f8f9fa', 'important');
            box.style.setProperty('background', '#f8f9fa', 'important');
            box.style.setProperty('color', 'inherit', 'important');
            box.style.setProperty('border', '1px solid #dee2e6', 'important');
        }
    }

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
            box.style.fontSize = '0.8rem';
            box.style.fontFamily = 'inherit';
            applyTheme(box);
            watchTheme(box);
        }

        // jednorádkový obsah
        box.innerHTML = `
            <i class="fas fa-boxes" style="margin-right:0.5em;"></i>
            Celkový počet beden k expedici v označených zakázkách: <strong>${boxCountSum}</strong>        
            &nbsp;|&nbsp;
            <i class="fas fa-balance-scale" style="margin-right:0.5em;"></i>
            Celková brutto hmotnost beden k expedici v označených zakázkách: <strong>${weightSum.toFixed(1)} kg</strong>
        `;
        applyTheme(box);
    }

    document.querySelectorAll('input.action-select').forEach(function(checkbox) {
        checkbox.addEventListener('change', updateSummary);
    });
    const selectAll = document.getElementById('action-toggle');
    if (selectAll) selectAll.addEventListener('change', updateSummary);

    updateSummary();
});
