document.addEventListener('DOMContentLoaded', () => {
    const rows = document.getElementById('measurement-rows');
    const template = document.getElementById('measurement-empty-row');
    const total = document.getElementById('id_mereni-TOTAL_FORMS');
    const add = document.getElementById('add-measurement');
    if (!rows || !template || !total || !add) return;

    const markDeleted = () => {
        rows.querySelectorAll('.measurement-row').forEach(row => {
            const deleted = row.querySelector('input[name$="-DELETE"]').checked;
            row.classList.toggle('opacity-50', deleted);
        });
    };
    rows.addEventListener('change', markDeleted);
    add.classList.remove('d-none');
    add.addEventListener('click', () => {
        const index = Number(total.value);
        rows.insertAdjacentHTML('beforeend', template.innerHTML.replaceAll('__prefix__', index));
        total.value = index + 1;
        markDeleted();
        rows.lastElementChild.querySelector('input[name$="-hodnota"]').focus();
    });
    markDeleted();

    const configElement = document.getElementById('ochrana-kontroly-bedny');
    const form = document.getElementById('measurement-form');
    if (!configElement || !form) return;
    const config = JSON.parse(configElement.textContent);
    let hasControlDraft = false;
    try { hasControlDraft = Boolean(sessionStorage.getItem(config.draft_key)); } catch (_) { /* DB příznak platí i bez úložiště. */ }
    const pending = config.ceka_na_potvrzeni || hasControlDraft;
    const banner = document.getElementById('kontrola-neulozene');
    const bannerText = document.getElementById('kontrola-neulozene-text');
    const normalise = value => {
        const text = String(value).trim().replace(',', '.');
        return text !== '' && Number.isFinite(Number(text)) ? String(Number(text)) : text;
    };
    const saved = new Map(config.ulozene_mereni.map(item => [String(item.id), normalise(item.hodnota)]));
    const entries = () => Array.from(rows.querySelectorAll('.measurement-row')).flatMap((row, index) => {
        const id = row.querySelector('[name$="-id"]').value;
        const value = normalise(row.querySelector('[name$="-hodnota"]').value);
        if (row.querySelector('[name$="-DELETE"]').checked || (!id && value === '')) return [];
        return [[id || `new:${index}`, value]];
    });
    const measurementDirty = () => {
        const values = entries();
        return values.length !== saved.size || values.some(([id, value]) => saved.get(id) !== value);
    };
    const refresh = () => {
        const dirty = measurementDirty();
        rows.querySelectorAll('.measurement-row').forEach(row => {
            const id = row.querySelector('[name$="-id"]').value;
            const input = row.querySelector('[name$="-hodnota"]');
            const deleted = row.querySelector('[name$="-DELETE"]').checked;
            input.classList.toggle('kontrola-zmeneno', id
                ? deleted || normalise(input.value) !== saved.get(id)
                : !deleted && normalise(input.value) !== '');
        });
        banner.classList.toggle('d-none', !dirty && !pending);
        bannerText.textContent = dirty
            ? 'Máte neuložené hodnoty měření. Nejprve je uložte.'
            : 'Po úpravě měření se vraťte na kontrolu této bedny a uložte výstupní kontrolu.';
    };
    rows.addEventListener('input', refresh);
    rows.addEventListener('change', refresh);
    add.addEventListener('click', refresh);
    window.createKontrolaNavigationGuard({
        form,
        isDirty: () => measurementDirty() || (config.zkontrolovana && pending),
        isBlocked: () => measurementDirty() || (config.zkontrolovana && pending),
        preserve: () => {},
        allowUrl: url => !measurementDirty() && url.origin === window.location.origin && (
            url.pathname === config.url_kontroly || config.urls_mereni.includes(url.pathname)
        ),
        onBlocked: () => {
            refresh();
            banner.classList.remove('d-none');
            banner.scrollIntoView({behavior: 'smooth', block: 'center'});
        },
    });
    refresh();
});
