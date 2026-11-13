document.addEventListener('DOMContentLoaded', () => {
    const masterInputs = Array.from(document.querySelectorAll('input[name="fakturovat"]'));
    if (!masterInputs.length) return;

    const operations = ['kaleni', 'rovnani', 'tryskani', 'zinkovani'].map(operation => {
        const name = `fakturovat_${operation}`;
        const inputs = Array.from(document.querySelectorAll(`input[name="${name}"]`));
        if (!inputs.length) return null;
        const row = inputs[0].closest('.form-row');
        const mirror = document.createElement('input');
        mirror.type = 'hidden';
        mirror.name = name;
        mirror.disabled = true;
        inputs[0].parentElement.appendChild(mirror);
        return {inputs, row, mirror, disabled: inputs.map(input => input.disabled)};
    }).filter(Boolean);
    if (!operations.length) return;

    const note = document.createElement('p');
    note.id = 'billing-disabled-note';
    note.className = 'help';
    note.setAttribute('role', 'status');
    note.textContent = 'Celá bedna se nefakturuje. Nastavení jednotlivých operací se uplatní po zapnutí Fakturovat.';
    const masterRow = masterInputs[0].closest('.form-row');
    (masterRow || masterInputs[0].parentElement).appendChild(note);

    const emptyNote = document.createElement('p');
    emptyNote.id = 'billing-empty-note';
    emptyNote.className = 'errornote';
    emptyNote.setAttribute('role', 'alert');
    emptyNote.textContent = 'Při Fakturovat = Ano vyberte alespoň jednu operaci k fakturaci, nebo nastavte Fakturovat = Ne.';
    (masterRow || masterInputs[0].parentElement).appendChild(emptyNote);

    const update = () => {
        const selected = masterInputs.find(input => input.checked);
        const enabled = selected?.type === 'checkbox' ? selected.checked : selected?.value === 'True';
        note.hidden = enabled;
        const empty = enabled && operations.length === 4
            && operations.every(({inputs}) => inputs.find(input => input.checked)?.value === 'False');
        emptyNote.hidden = !empty;
        masterInputs.forEach(input => input.setCustomValidity(empty ? emptyNote.textContent : ''));
        operations.forEach(({inputs, row, mirror, disabled}) => {
            mirror.value = inputs.find(input => input.checked)?.value || '';
            // Disabled radios se neodesílají. Zrcadlo zachová vybranou hodnotu.
            mirror.disabled = enabled || disabled.every(Boolean);
            inputs.forEach((input, index) => { input.disabled = !enabled || disabled[index]; });
            row?.classList.toggle('billing-operation-disabled', !enabled);
        });
    };
    masterInputs.forEach(input => input.addEventListener('change', update));
    operations.forEach(({inputs}) => inputs.forEach(input => input.addEventListener('change', update)));
    window.addEventListener('pageshow', update);
    masterInputs[0].form?.addEventListener('reset', () => setTimeout(update, 0));
    update();
});
