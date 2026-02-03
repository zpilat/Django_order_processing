(function () {
    const config = window.bednaPollConfig || {};
    if (!config.pollUrl) {
        return;
    }

    const bannerId = 'bedna-change-banner';
    const storageKey = 'bedna-reload-after-action';
    const autoReloadActions = [];
    const interval = typeof config.intervalMs === 'number' && config.intervalMs > 0 ? config.intervalMs : 30000;
    let lastKnown = config.lastChange || null;
    let lastKnownId = typeof config.lastChangeId === 'number' ? config.lastChangeId : null;

    function showBanner() {
        // Avoid creating duplicate banners (top or inline)
        if (document.getElementById(bannerId) || document.getElementById(bannerId + '-inline')) {
            return;
        }

        // If the dedicated inline container exists in the toolbar, show an inline banner there
        const searchContainer = document.getElementById('bedna-change-container');
        if (searchContainer) {
            const inlineId = bannerId + '-inline';
            if (document.getElementById(inlineId)) return;


            const item = document.createElement('div');
            item.id = inlineId;
            // use admin-native warning class so it inherits admin styles
            item.className = 'warning';
            item.style.color = '#a00';

            const messageText = document.createElement('span');
            messageText.textContent = 'Data se změnila.';  
            messageText.style.display = 'inline-block';
            messageText.style.border = '1px solid #a00';
            messageText.style.padding = '0.25rem 0.5rem';
            messageText.style.borderRadius = '4px';

            const actionButton = document.createElement('button');
            actionButton.type = 'button';
            actionButton.className = 'button';
            actionButton.textContent = 'Obnovit';
            actionButton.style.marginLeft = '0.75rem';
            // slightly larger / more prominent button
            actionButton.style.padding = '0.3rem 0.8rem';
            actionButton.style.fontSize = '0.85rem';
            actionButton.style.fontWeight = '400';
            actionButton.style.borderRadius = '4px';
            actionButton.addEventListener('click', function (event) {
                event.preventDefault();
                window.location.reload();
            });

            item.appendChild(messageText);
            item.appendChild(actionButton);

            // Insert into the dedicated container
            searchContainer.appendChild(item);
            return;
        }

        // Fallback: original top-of-content banner
        const content = document.querySelector('#content');
        if (!content) {
            return;
        }
        const list = document.createElement('ul');
        list.className = 'messagelist';
        list.id = bannerId;

        const item = document.createElement('li');
        item.className = 'warning';
        item.style.color = '#a00';

        const messageText = document.createElement('span');
        messageText.textContent = 'Data se změnila.';
        messageText.style.display = 'inline-block';
        messageText.style.border = '1px solid #a00';
        messageText.style.padding = '0.25rem 0.5rem';
        messageText.style.borderRadius = '4px';

        const actionButton = document.createElement('button');
        actionButton.type = 'button';
        actionButton.className = 'button';
        actionButton.textContent = 'Obnovit';
        actionButton.style.marginLeft = '0.75rem';
        // make fallback button similar style for consistency
        actionButton.style.padding = '0.3rem 0.9rem';
        actionButton.style.fontSize = '0.85rem';
        actionButton.style.fontWeight = '400';
        actionButton.style.borderRadius = '4px';
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
            if (lastKnownId) {
                url.searchParams.set('since_id', lastKnownId);
            } else if (lastKnown) {
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
                        if (typeof data.history_id === 'number') {
                            lastKnownId = data.history_id;
                        }
                    } else if (data.changed) {
                        if (shouldAutoReload()) {
                            clearAutoReloadFlag();
                            window.location.reload();
                            return;
                        }
                        showBanner();
                    } else if (typeof data.history_id === 'number') {
                        lastKnownId = data.history_id;
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
