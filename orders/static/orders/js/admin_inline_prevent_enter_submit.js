document.addEventListener('DOMContentLoaded', function() {
    const forms = Array.from(document.querySelectorAll('#kamion_form, #sarzekrok_form'));
    if (!forms.length) {
        return;
    }

    function isVisible(el) {
        return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
    }

    function isNavigableField(el) {
        if (!(el instanceof HTMLElement)) {
            return false;
        }

        if (!el.matches('input, select, textarea')) {
            return false;
        }

        if (el.closest('.submit-row')) {
            return false;
        }

        if (el.matches('input[type="hidden"], input[type="submit"], input[type="button"], input[type="checkbox"], input[type="radio"], input[type="file"]')) {
            return false;
        }

        if (el.disabled || el.readOnly || !isVisible(el)) {
            return false;
        }

        return true;
    }

    function findManagedFormForElement(el) {
        if (!(el instanceof HTMLElement)) {
            return null;
        }

        const ownForm = el.closest('#kamion_form, #sarzekrok_form');
        return ownForm || null;
    }

    function focusNextField(form, currentField, backwards) {
        const fields = Array.from(form.querySelectorAll('input, select, textarea')).filter(isNavigableField);
        const currentIndex = fields.indexOf(currentField);

        if (currentIndex === -1) {
            return;
        }

        const nextIndex = backwards ? currentIndex - 1 : currentIndex + 1;
        if (nextIndex < 0 || nextIndex >= fields.length) {
            return;
        }

        const nextField = fields[nextIndex];
        nextField.focus();
        if (nextField instanceof HTMLInputElement && /^(text|search|tel|url|email|password|number)$/i.test(nextField.type)) {
            nextField.select();
        }
    }

    function resolveAnchorField(form, target) {
        if (!(target instanceof HTMLElement)) {
            return null;
        }

        if (isNavigableField(target)) {
            return target;
        }

        return null;
    }

    document.addEventListener('keydown', function(event) {
        if (event.key !== 'Enter') {
            return;
        }

        const target = event.target;
        if (!(target instanceof HTMLElement)) {
            return;
        }

        const managedForm = findManagedFormForElement(target);
        if (!managedForm) {
            return;
        }

        const anchorField = resolveAnchorField(managedForm, target);
        if (!anchorField) {
            return;
        }

        event.preventDefault();

        // U selectů vracíme původní chování (jen blokace submitu, bez posunu fokusu).
        if (anchorField instanceof HTMLSelectElement) {
            return;
        }

        focusNextField(managedForm, anchorField, event.shiftKey);
    }, true);
});
