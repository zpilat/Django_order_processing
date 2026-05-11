document.addEventListener('DOMContentLoaded', function() {
    const inlineGroup = document.getElementById('zakazky_prijem-group');
    if (!inlineGroup) {
        return;
    }

    inlineGroup.addEventListener('keydown', function(event) {
        if (event.key !== 'Enter') {
            return;
        }

        const target = event.target;
        if (!(target instanceof HTMLElement)) {
            return;
        }

        // Blokujeme Enter jen pro vstupní pole inlinu, ne pro submit tlačítka.
        const isInlineField = target.matches('input, select')
            && !target.matches('input[type="submit"], input[type="button"], input[type="checkbox"], input[type="radio"]');

        if (isInlineField) {
            event.preventDefault();
        }
    });
});
