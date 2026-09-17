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
});
