document.addEventListener('DOMContentLoaded', () => {
    const uvolneni = document.getElementById('id_uvolneni');
    const duvody = document.getElementById('duvody-neshody');
    const cistota = document.getElementById('id_cistota');
    const ulozeni = document.getElementById('id_ulozeni');
    const poznamka = document.getElementById('id_poznamka');
    const pravidlaElement = document.getElementById('pravidla-kontroly-bedny');
    if (!uvolneni || !duvody || !cistota || !ulozeni || !pravidlaElement) return;

    const pravidla = JSON.parse(pravidlaElement.textContent);
    const omezeniCistoty = document.getElementById('omezeni-cistoty');
    const omezeniUlozeni = document.getElementById('omezeni-ulozeni');
    const checkboxes = Array.from(duvody.querySelectorAll('input[type="checkbox"]'));
    const aktualizovatMoznostiUvolneni = vyber => {
        const povolene = cistota.value === 'NOK' || ulozeni.value === 'NOK'
            ? ['NE'] : pravidla.povolene_stavy_prohybu;
        const moznosti = pravidla.uvolneni.filter(([value]) => povolene.includes(value));
        uvolneni.replaceChildren(...moznosti.map(([value, label]) => new Option(label, value)));
        uvolneni.value = povolene.includes(vyber) ? vyber : moznosti[0][0];
    };
    let predchoziUlozeniNok = (pravidla.puvodni_ulozeni ?? ulozeni.value) === 'NOK';
    let track = () => {};
    const aktualizovat = () => {
        if (pravidla.can_edit) {
            const cistotaNok = cistota.value === 'NOK';
            const ulozeniNok = ulozeni.value === 'NOK';
            if (predchoziUlozeniNok && !ulozeniNok && !poznamka?.value.trim()) {
                const jine = checkboxes.find(checkbox => checkbox.name === 'neshoda_jine');
                if (jine) jine.checked = false;
            }
            predchoziUlozeniNok = ulozeniNok;
            aktualizovatMoznostiUvolneni(uvolneni.value);
            omezeniCistoty?.classList.toggle('d-none', !cistotaNok);
            omezeniUlozeni?.classList.toggle('d-none', !ulozeniNok);

            const automaticke = {
                neshoda_krivost: pravidla.krivost,
                neshoda_cistota: cistotaNok,
            };
            if (ulozeniNok) automaticke.neshoda_jine = true;
            const uvolneno = uvolneni.value === 'UV';
            checkboxes.forEach(checkbox => {
                const automaticky = Object.hasOwn(automaticke, checkbox.name);
                if (uvolneno) checkbox.checked = false;
                else if (automaticky) checkbox.checked = automaticke[checkbox.name];
                checkbox.disabled = uvolneno || automaticky;
            });
        }
        duvody.classList.toggle('d-none', !['NE', 'UO', 'UV'].includes(uvolneni.value));
        track();
    };

    uvolneni.addEventListener('change', aktualizovat);
    cistota.addEventListener('change', aktualizovat);
    ulozeni.addEventListener('change', aktualizovat);
    checkboxes.forEach(checkbox => checkbox.addEventListener('change', aktualizovat));
    aktualizovat();

    const configElement = document.getElementById('ochrana-kontroly-bedny');
    const form = document.getElementById('control-form');
    if (!configElement || !form || !pravidla.can_edit) return;
    const config = JSON.parse(configElement.textContent);
    const fields = Array.from(form.querySelectorAll('input[name], select[name], textarea[name]'))
        .filter(field => Object.hasOwn(config.ulozene_hodnoty, field.name));
    const snapshot = form.querySelector('[name="snapshot"]');
    const banner = document.getElementById('kontrola-neulozene');
    const bannerText = document.getElementById('kontrola-neulozene-text');
    const conflict = document.getElementById('kontrola-konflikt-konceptu');
    const save = form.querySelector('[type="submit"]');
    const pending = config.ceka_na_potvrzeni || config.stavy_nepotvrzeny;
    let discardingDraft = false;
    const normalise = (field, value) => {
        if (field.type === 'checkbox') return Boolean(value);
        const text = String(value ?? '').replaceAll('\r\n', '\n').trim();
        if (field.type === 'number' && text !== '' && Number.isFinite(Number(text))) return String(Number(text));
        return text;
    };
    const fieldValue = field => normalise(field, field.type === 'checkbox' ? field.checked : field.value);
    const changed = () => fields.filter(field => fieldValue(field) !== normalise(field, config.ulozene_hodnoty[field.name]));
    const isDirty = () => pending || changed().length > 0;
    const removeDraft = () => {
        try { sessionStorage.removeItem(config.draft_key); } catch (_) { /* Navigace se řídí i živým formulářem. */ }
    };
    const preserve = () => {
        if (discardingDraft) return true;
        if (!isDirty()) { removeDraft(); return true; }
        try {
            sessionStorage.setItem(config.draft_key, JSON.stringify({
                version: 1, snapshot: snapshot.value,
                values: Object.fromEntries(fields.map(field => [field.name, fieldValue(field)])),
                baseline: config.ulozene_hodnoty, kontrola_existovala: config.kontrola_existuje,
            }));
            return true;
        } catch (_) { return false; }
    };

    // Koncept je v rámci karty prohlížeče oddělený podle uživatele a bedny.
    if (!config.is_bound) {
        let draft;
        try { draft = JSON.parse(sessionStorage.getItem(config.draft_key)); } catch (_) { /* Koncept není dostupný. */ }
        if (draft?.version === 1 && draft.values && typeof draft.snapshot === 'string') {
            const matchesDatabase = fields.every(field =>
                normalise(field, draft.values[field.name]) === normalise(field, config.ulozene_hodnoty[field.name]));
            if (matchesDatabase && !pending) {
                // Úspěšné uložení poznáme podle skutečných hodnot z DB, nikoli pouhého submitu.
                removeDraft();
            } else {
                fields.forEach(field => {
                    if (field === uvolneni || !Object.hasOwn(draft.values, field.name)) return;
                    if (field.type === 'checkbox') field.checked = Boolean(draft.values[field.name]);
                    else field.value = draft.values[field.name] ?? '';
                });
                // Volba z konceptu může chybět v možnostech odvozených z DB.
                // Nejdříve obnovit nabídku podle rozepsané Čistoty a Uložení.
                aktualizovatMoznostiUvolneni(draft.values[uvolneni.name] ?? uvolneni.value);
                snapshot.value = draft.snapshot;
                // První měření může vytvořit dosud neexistující prázdnou kontrolu.
                // Nový snapshot přijmout jen pokud všechny původní hodnoty zůstaly stejné.
                if (draft.kontrola_existovala === false && config.kontrola_existuje && draft.baseline &&
                    fields.every(field => Object.hasOwn(draft.baseline, field.name) &&
                        normalise(field, draft.baseline[field.name]) === normalise(field, config.ulozene_hodnoty[field.name]))) {
                    snapshot.value = config.snapshot;
                }
            }
        }
    }
    const showSave = () => {
        bannerText.textContent = 'Nejprve uložte výstupní kontrolu bedny. Neuložené změny jsou označené červeně.';
        banner.classList.remove('d-none');
        banner.scrollIntoView({behavior: 'smooth', block: 'center'});
    };
    track = () => {
        const changes = new Set(changed());
        fields.forEach(field => {
            field.classList.toggle('kontrola-zmeneno', changes.has(field));
            document.querySelector(`label[for="${field.id}"]`)?.classList.toggle('kontrola-zmeneny-popisek', changes.has(field));
        });
        const dirty = isDirty();
        form.dataset.kontrolaNeulozene = String(dirty);
        banner.classList.toggle('d-none', !dirty);
        bannerText.textContent = changes.size
            ? 'Máte neuložené změny kontroly. Změněné hodnoty jsou označené červeně.'
            : 'Po změně měření se změnilo vyhodnocení kontroly nebo technologických stavů. Zkontrolujte a uložte výstupní kontrolu bedny.';
        save.classList.toggle('btn-danger', dirty);
        save.classList.toggle('btn-primary', !dirty);
        conflict.classList.toggle('d-none', snapshot.value === config.snapshot);
        preserve();
    };
    form.addEventListener('input', track);
    form.addEventListener('change', track);
    document.getElementById('kontrola-prejit-na-ulozeni').addEventListener('click', () => {
        save.scrollIntoView({behavior: 'smooth', block: 'center'});
        save.focus({preventScroll: true});
    });

    let guard;
    const reloadDatabase = () => {
        if (!window.confirm('Zahodit rozepsanou kopii a načíst aktuální uložené údaje?')) return;
        discardingDraft = true;
        removeDraft();
        guard.allowNavigation();
        window.location.assign(config.url_kontroly);
    };
    document.getElementById('kontrola-nacist-db').addEventListener('click', reloadDatabase);
    document.addEventListener('click', event => {
        if (!event.target.closest('[data-reload-control]')) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        reloadDatabase();
    }, true);
    guard = window.createKontrolaNavigationGuard({
        form, isDirty, preserve,
        isBlocked: () => config.zkontrolovana && isDirty(),
        allowUrl: url => url.origin === window.location.origin && config.urls_mereni.includes(url.pathname) && preserve(),
        onBlocked: showSave,
    });
    aktualizovat();
});
