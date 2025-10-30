(function () {
    const config = window.bednaPollConfig || {};
    if (!config.pollUrl) {
        return;
    }

    const bannerId = 'bedna-change-banner';
    const storageKey = 'bedna-reload-after-action';
    const autoReloadActions = ['oznacit_rovna_se_action'];
    const interval = typeof config.intervalMs === 'number' && config.intervalMs > 0 ? config.intervalMs : 30000;
    let lastKnown = config.lastChange || null;

    function showBanner() {
        if (document.getElementById(bannerId)) {
            return;
        }
        const content = document.querySelector('#content');
        if (!content) {
            return;
        }
        const list = document.createElement('ul');
        list.className = 'messagelist';
        list.id = bannerId;

        const item = document.createElement('li');
        item.className = 'warning';
        const messageText = document.createElement('span');
        messageText.textContent = 'Data se změnila.';

        const actionButton = document.createElement('button');
        actionButton.type = 'button';
        actionButton.className = 'button';
        actionButton.textContent = 'Obnovit';
        actionButton.style.marginLeft = '0.75rem';
        actionButton.addEventListener('click', function (event) {
            event.preventDefault();
            window.location.reload();
        });

        item.appendChild(messageText);
        item.appendChild(actionButton);
        list.appendChild(item);
        content.insertBefore(list, content.firstChild);
    }

    function shouldAutoReload() {
        try {
            return window.sessionStorage && window.sessionStorage.getItem(storageKey) === '1';
        } catch (err) {
            return false;
        }
    }

    function clearAutoReloadFlag() {
        try {
            if (window.sessionStorage) {
                window.sessionStorage.removeItem(storageKey);
            }
        } catch (err) {
            /* ignore storage errors */
        }
    }

    function rememberActionSubmit(event) {
        const form = event.target;
        if (!form || form.tagName !== 'FORM') {
            return;
        }
        const actionSelect = form.querySelector('select[name="action"]');
        if (!actionSelect) {
            return;
        }
        const value = actionSelect.value;
        try {
            if (window.sessionStorage && autoReloadActions.indexOf(value) !== -1) {
                window.sessionStorage.setItem(storageKey, '1');
            } else if (window.sessionStorage) {
                window.sessionStorage.removeItem(storageKey);
            }
        } catch (err) {
            /* ignore storage errors */
        }
    }

    function poll() {
        try {
            const url = new URL(config.pollUrl, window.location.origin);
            if (lastKnown) {
                url.searchParams.set('since', lastKnown);
            }
            fetch(url.toString(), { credentials: 'same-origin' })
                .then(function (response) {
                    if (!response || !response.ok) {
                        return null;
                    }
                    return response.json();
                })
                .then(function (data) {
                    if (!data) {
                        return;
                    }
                    if (data.timestamp) {
                        if (lastKnown && data.changed) {
                            if (shouldAutoReload()) {
                                clearAutoReloadFlag();
                                window.location.reload();
                                return;
                            }
                            showBanner();
                        }
                        lastKnown = data.timestamp;
                    } else if (data.changed) {
                        if (shouldAutoReload()) {
                            clearAutoReloadFlag();
                            window.location.reload();
                            return;
                        }
                        showBanner();
                    }
                })
                .catch(function () { /* swallow fetch errors */ });
        } catch (err) {
            // ignore malformed URLs
        }
    }

    function schedulePolling() {
        if (interval <= 0) {
            return;
        }
            poll();
            setInterval(poll, interval);
    }

        function init() {
            schedulePolling();
            const form = document.getElementById('changelist-form');
            if (form) {
                form.addEventListener('submit', rememberActionSubmit, true);
            }
        }

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', init);
        } else {
            init();
        }
})();
