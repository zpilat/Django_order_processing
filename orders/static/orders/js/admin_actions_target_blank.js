document.addEventListener('DOMContentLoaded', function () {
    // Seznam akcí, které se mají otevírat v novém panelu
    const actionsTargetBlank = [
        'tisk_karet_beden_action',
        'tisk_karet_beden_zakazek_action',
        'tisk_karet_beden_kamionu_action',
        'tisk_karet_bedny_a_kontroly_action',
        'tisk_dodaciho_listu_kamionu_action',
        'tisk_proforma_faktury_kamionu_action',
        'tisk_karet_kontroly_kvality_action',
        'tisk_karet_kontroly_kvality_zakazek_action',
        'tisk_karet_kontroly_kvality_kamionu_action',
        'tisk_protokolu_kamionu_vydej_action',
        'oznacit_rovna_se_action',
        'tisk_rozpracovanost_action',
    ];

    // Najdi hlavní formulář v adminu podle id (nejbezpečnější)
    const actionForm = document.getElementById('changelist-form');
    if (!actionForm) return;

    actionForm.addEventListener('submit', function() {
        const actionSelects = actionForm.querySelectorAll('select[name="action"]');
        if (!actionSelects.length) return;

        let selectedAction = '';
        actionSelects.forEach(select => {
            if (select && select.value && select.value !== '__model__' && select.value !== '') {
                selectedAction = select.value;
            }
        });

        let explicitTarget = null;
        if (selectedAction === 'oznacit_rovna_se_action') {
            try {
                const windowName = 'bedna_rovnani_print';
                window.open('', windowName);
                explicitTarget = windowName;
            } catch (err) {
                explicitTarget = null;
            }
        }

        if (actionsTargetBlank.includes(selectedAction)) {
            actionForm.setAttribute('target', explicitTarget || '_blank');
        } else {
            actionForm.removeAttribute('target');
        }

        if (selectedAction === 'oznacit_rovna_se_action') {
            setTimeout(function () {
                try {
                    if (window.sessionStorage) {
                        window.sessionStorage.removeItem('bedna-reload-after-action');
                    }
                } catch (err) {
                    /* ignore storage errors */
                }
                window.location.reload();
            }, 1000);
        }
    });
});
