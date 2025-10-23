document.addEventListener('DOMContentLoaded', function () {
    // Seznam akcí, které se mají otevírat v novém panelu
    const actionsTargetBlank = [
        'tisk_karet_beden_action',
        'tisk_karet_beden_zakazek_action',
        'tisk_karet_beden_kamionu_action',
        'tisk_dodaciho_listu_kamionu_action',
        'tisk_proforma_faktury_kamionu_action',
        'tisk_karet_kontroly_kvality_action',
        'tisk_karet_kontroly_kvality_zakazek_action',
        'tisk_karet_kontroly_kvality_kamionu_action',
        'oznacit_rovna_se_action',
    ];

    // Najdi hlavní formulář v adminu podle id (nejbezpečnější)
    const actionForm = document.getElementById('changelist-form');
    if (!actionForm) return;

    actionForm.addEventListener('submit', function(e) {
        const actionSelect = actionForm.querySelector('select[name="action"]');
        if (!actionSelect) return;

        const selectedAction = actionSelect.value;
        if (actionsTargetBlank.includes(selectedAction)) {
            actionForm.setAttribute('target', '_blank');
        } else {
            actionForm.removeAttribute('target');
        }
    });
});
