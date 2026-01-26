document.addEventListener('DOMContentLoaded', function() {
    const params = new URLSearchParams(window.location.search);
    if (params.get('stav_bedny') !== 'KE') return; // only for K_EXPEDICI filter

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
        let boxCount = 0;

        document.querySelectorAll('input.action-select:checked').forEach(function(checkbox) {
            const row = checkbox.closest('tr');
            if (!row) return;

            // Brutto hmotnost bedny (hmotnost + tara)
            const weightCell = row.querySelector('td.field-get_hmotnost_brutto');
            if (weightCell) {
                const val = parseFloat(weightCell.textContent.replace(',', '.'));
                if (!isNaN(val)) weightSum += val;
            }

            boxCount += 1;
        });

        let box = document.getElementById('bedny-summary');
        if (!box) {
            box = document.createElement('div');
            box.id = 'bedny-summary';
            box.className = 'info';
            box.style.marginBottom = '0.75em';
            box.style.padding = '0.5em 0.75em';
            box.style.fontSize = '0.85rem';
            applyTheme(box);
            watchTheme(box);
            resultsTable.parentNode.insertBefore(box, resultsTable);
        }

        box.innerHTML = `
            <i class="fas fa-box" style="margin-right:0.5em;"></i>
            Počet beden vybraných k expedici: <strong>${boxCount}</strong>
            &nbsp;|&nbsp;
            <i class="fas fa-balance-scale" style="margin-right:0.5em;"></i>
            Celková brutto hmotnost beden vybraných k expedici: <strong>${weightSum.toFixed(1)} kg</strong>
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
