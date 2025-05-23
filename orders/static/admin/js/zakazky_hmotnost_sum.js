document.addEventListener('DOMContentLoaded', function() {
    function updateSum() {
        let sum = 0;
        document.querySelectorAll('input.action-select:checked').forEach(function(checkbox) {
            const row = checkbox.closest('tr');
            const hmotnostCell = row.querySelector('td.field-hmotnost_zakazky');
            if (hmotnostCell) {
                let val = parseFloat(hmotnostCell.textContent.replace(',', '.'));
                if (!isNaN(val)) sum += val;
            }
        });
        let box = document.getElementById('hmotnost-sum-box');
        if (!box) {
            box = document.createElement('div');
            box.id = 'hmotnost-sum-box';
            box.className = 'alert alert-info shadow-sm';
            box.style = 'position:fixed;top:100px;right:300px;z-index:1000;min-width:260px;max-width:350px;padding:.75rem 1.25rem;display:flex;align-items:center;font-size:1rem;font-family:inherit;';
            document.body.appendChild(box);
        } else {
            box.className = 'alert alert-info shadow-sm'; // jistota správné třídy
        }
        box.innerHTML = `<i class="fas fa-balance-scale" style="margin-right:0.5em;color:#0174c6;"></i> Hmotnost označených zakázek:<strong><span style="margin-left:0.5em;">${sum.toFixed(1)} kg</span></strong>`;
    }

    // Na všechny jednotlivé checkboxy
    document.querySelectorAll('input.action-select').forEach(function(checkbox) {
        checkbox.addEventListener('change', updateSum);
    });

    // **Na hlavní (select all) checkbox**
    let selectAll = document.getElementById('action-toggle');
    if (selectAll) {
        selectAll.addEventListener('change', function() {
            // Všechni checkboxy se zaškrtnou/odškrtnou, ale 'change' event na jednotlivých se nevyvolá!
            // Proto se ručně zavolá updateSum (a případně simuluje změna na všech)
            updateSum();
        });
    }

    // Spustit na načtení stránky
    updateSum();
});


