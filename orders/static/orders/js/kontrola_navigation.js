// Ochrana běžné navigace; zavření karty a tlačítka prohlížeče mohou pouze varovat.
window.createKontrolaNavigationGuard = ({form, isDirty, isBlocked, preserve, allowUrl, onBlocked}) => {
    let navigating = false;
    const allowNavigation = () => { navigating = true; };
    document.addEventListener('click', event => {
        const link = event.target.closest('a[href]');
        if (!link || event.defaultPrevented || !isDirty()) return;
        const url = new URL(link.href, window.location.href);
        if (url.pathname === window.location.pathname && url.search === window.location.search && url.hash) return;
        if (allowUrl(url, link)) {
            // Ctrl+klik či target=_blank ponechává tuto stránku otevřenou.
            preserve();
            if (!event.ctrlKey && !event.metaKey && !event.shiftKey && link.target !== '_blank') navigating = true;
            queueMicrotask(() => { if (event.defaultPrevented) navigating = false; });
            return;
        }
        if (isBlocked()) {
            event.preventDefault();
            event.stopImmediatePropagation();
            onBlocked();
        }
    }, true);
    document.addEventListener('submit', event => {
        if (event.target === form) {
            preserve();
            navigating = true;
            queueMicrotask(() => { if (event.defaultPrevented) navigating = false; });
        } else if (isDirty() && isBlocked()) {
            event.preventDefault();
            event.stopImmediatePropagation();
            onBlocked();
        }
    }, true);
    window.addEventListener('beforeunload', event => {
        preserve();
        if (!navigating && isDirty()) {
            event.preventDefault();
            event.returnValue = '';
        }
    });
    window.addEventListener('pageshow', event => {
        navigating = false;
        if (event.persisted) {
            // Po návratu z měření nesmí cache obnovit zastaralé podmínky kontroly.
            preserve();
            navigating = true;
            window.location.reload();
        }
    });
    return {allowNavigation};
};
