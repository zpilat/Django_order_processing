// Skript se spustí až po načtení celé stránky, aby byly dostupné všechny HTML prvky.
document.addEventListener('DOMContentLoaded', function() {
    // Ve výpisu beden běží souhrn pouze pro filtr "Přijato" (stav_bedny = PR).
    const params = new URLSearchParams(window.location.search);
    if (params.get('stav_bedny') !== 'PR') return;

    // Tabulka s výsledky v Django adminu.
    const resultsTable = document.getElementById('result_list');
    if (!resultsTable) return;

    const darkQuery = window.matchMedia('(prefers-color-scheme: dark)');

    // Zjištění explicitně nastaveného tématu (pokud je v HTML data-theme).
    const themeAttr = () => (document.documentElement.dataset.theme || document.body.dataset.theme || '').toLowerCase();

    /**
     * Vrátí true, pokud má být souhrnný box vykreslen v tmavém režimu.
     * Priorita:
     * 1) explicitní data-theme,
     * 2) systémové nastavení,
     * 3) CSS třída "dark" na html/body.
     */
    const isDark = () => {
        const t = themeAttr();
        if (t === 'light') return false;
        if (t === 'dark') return true;
        return darkQuery.matches
            || document.documentElement.classList.contains('dark')
            || document.body.classList.contains('dark');
    };

    /**
     * Sleduje změny motivu stránky a při změně ihned upraví vzhled souhrnného boxu.
     * @param {HTMLDivElement} box - Element, který zobrazuje souhrn beden.
     */
    function watchTheme(box) {
        const observer = new MutationObserver(() => applyTheme(box));
        observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'data-theme'] });
        observer.observe(document.body, { attributes: true, attributeFilter: ['class', 'data-theme'] });
        darkQuery.addEventListener('change', () => applyTheme(box));
    }

    /**
     * Nastaví barvy boxu podle aktivního režimu (dark/light), aby vizuálně zapadl do adminu.
     * @param {HTMLDivElement} box - Element, kterému se nastavuje vzhled.
     */
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

    /**
     * Přepočítá a zobrazí souhrn pro aktuálně zaškrtnuté bedny:
     * - celkovou netto hmotnost (sloupec hmotnost) v kg.
     */
    function updateSummary() {
        let weightSum = 0;

        // Projde všechny zaškrtnuté checkboxy v akčním sloupci tabulky.
        document.querySelectorAll('input.action-select:checked').forEach(function(checkbox) {
            const row = checkbox.closest('tr');
            if (!row) return;

            // Netto hmotnost bedny (hmotnost):
            // 1) v editable režimu je hodnota v inputu,
            // 2) jinak fallback na text buňky.
            const weightCell = row.querySelector('td.field-hmotnost');
            if (weightCell) {
                const weightInput = weightCell.querySelector('input, textarea, select');
                const rawValue = weightInput
                    ? (weightInput.value || '')
                    : (weightCell.textContent || '');

                const normalized = rawValue
                    .trim()
                    .replace(/\s/g, '')
                    .replace(',', '.');

                const val = parseFloat(normalized);
                if (!isNaN(val)) weightSum += val;
            }
        });

        // Box vytvoříme jen jednou, další přepočty už jen mění jeho obsah.
        let box = document.getElementById('bedny-summary');
        if (!box) {
            box = document.createElement('div');
            box.id = 'bedny-summary';
            box.className = 'info';
            box.style.marginBottom = '0.75em';
            box.style.padding = '0.5em 0.75em';
            box.style.fontSize = '0.85rem';
            box.style.display = 'flex';
            box.style.alignItems = 'center';
            box.style.gap = '0.35em';
            box.style.lineHeight = '1.35';
            applyTheme(box);
            watchTheme(box);
            resultsTable.parentNode.insertBefore(box, resultsTable);
        }

        box.innerHTML = `
            <i class="fas fa-balance-scale" style="margin-right:0.5em;"></i>
            <span>Celková netto hmotnost vybraných beden:</span>
            <strong style="font-size:0.95rem; white-space:nowrap;">${weightSum.toFixed(1)} kg</strong>
        `;
        applyTheme(box);
    }

    // Reakce na změnu výběru jednotlivých řádků.
    document.querySelectorAll('input.action-select').forEach(function(checkbox) {
        checkbox.addEventListener('change', updateSummary);
    });

    // Reakce na úpravu hmotnosti v editable sloupci (Přijato).
    document.querySelectorAll('td.field-hmotnost input, td.field-hmotnost textarea, td.field-hmotnost select').forEach(function(field) {
        field.addEventListener('input', updateSummary);
        field.addEventListener('change', updateSummary);
    });

    // Reakce na globální checkbox "vybrat vše".
    const selectAll = document.getElementById('action-toggle');
    if (selectAll) selectAll.addEventListener('change', updateSummary);

    // Po načtení stránky ihned vykreslí počáteční stav souhrnu.
    updateSummary();
});
