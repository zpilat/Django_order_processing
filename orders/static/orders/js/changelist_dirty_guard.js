// filepath: /home/zpilat/Python/Django_order_processing/orders/static/orders/changelist_dirty_guard.js
/* global django */
(function () {
  const $ = (window.django && window.django.jQuery) || window.jQuery;
  if (!$) return;

  const formSel = '#changelist-form';
  let dirty = false;

  function isChangedFromDefault(el) {
    if (!el) return false;
    const tag = (el.tagName || '').toLowerCase();
    const type = (el.type || '').toLowerCase();

    if (type === 'checkbox' || type === 'radio') {
      return !!el.checked !== !!el.defaultChecked;
    }

    if (tag === 'select') {
      const opts = el.options || [];
      for (let i = 0; i < opts.length; i += 1) {
        if (!!opts[i].selected !== !!opts[i].defaultSelected) {
          return true;
        }
      }
      return false;
    }

    return (el.value || '') !== (el.defaultValue || '');
  }

  function ensureWarning() {
    // Preferované chování: pokud existuje speciální kontejner ve search baru,
    // vlož tam jednoduchý inline element. Jinak fallback na původní messagelist nahoře.
    const searchContainer = document.getElementById('dirty-warning-container');
    if (searchContainer) {
      let item = document.getElementById('dirty-warning');
      if (!item) {
        // Use admin-native warning class so the message inherits admin styles
    item = document.createElement('div');
    item.id = 'dirty-warning';
    item.className = 'warning';
    item.textContent = 'Máte neuložené změny.';
    item.style.display = 'none';
    // Make the text color red per request
    item.style.color = '#a00';
    item.style.border = '1px solid #a00';
    item.style.padding = '0.25rem 0.5rem';
    item.style.borderRadius = '4px';
    // keep it inline in the toolbar
    item.style.display = 'none';
        searchContainer.appendChild(item);
      }
      return item;
    }

    // Fallback: původní chování v messagelist (horní část stránky)
    const content = document.getElementById('content') || document.body;
    let list = content.querySelector('ul.messagelist');
    if (!list) {
      list = document.createElement('ul');
      list.className = 'messagelist';
      content.insertBefore(list, content.firstChild);
    }
    let item = document.getElementById('dirty-warning');
    if (!item) {
      // Create a list item using admin-native 'warning' class
      item = document.createElement('li');
      item.id = 'dirty-warning';
      item.className = 'warning';
      item.textContent = 'Máte neuložené změny. Nezapomeňte uložit.';
      item.style.display = 'none';
      // Make the text color red for fallback as well
      item.style.color = '#a00';
      list.appendChild(item);
    }
    return item;
  }

  function showWarning() {
    const item = ensureWarning();
    // Pokud je to LI (flood do messagelist), zobraz jako list-item, jinak inline-block
    if (item && item.tagName && item.tagName.toLowerCase() === 'li') {
      item.style.display = 'list-item';
    } else if (item) {
      item.style.display = 'inline-block';
    }
  }

  function hideWarning() {
    const item = document.getElementById('dirty-warning');
    if (item) item.style.display = 'none';
  }

  function isDataField(el) {
    const name = el && el.name ? el.name : '';
    if (!name) return false;
    if (el.type === 'hidden') return false;
    // management fields formsetu
    if (/-TOTAL_FORMS$|-INITIAL_FORMS$|-MIN_NUM_FORMS$|-MAX_NUM_FORMS$/.test(name)) return false;
    // admin akční pole a výběry řádků
    if (name === 'action' || name === '_selected_action' || name === 'select_across' || name === 'index') return false;
    return true;
  }

  $(function () {
    const $form = $(formSel);
    if ($form.length === 0) return;

    // Dirty jen při uživatelské změně skutečných datových polí
    $(document).on('change', formSel + ' :input', function (e) {
      if (!isDataField(e.target)) return;
      dirty = true;
      showWarning();
    });

    // Při odeslání formuláře zrušit varování
    $(document).on('submit', formSel, function () {
      const formEl = this;
      // odstranit staré markery, pokud by došlo k opakovanému submitu
      const stale = formEl.querySelectorAll('input[name="_touched_field"], input[name="_touched_enabled"]');
      stale.forEach((el) => el.remove());

      // marker, že touched režim je aktivní
      const enabled = document.createElement('input');
      enabled.type = 'hidden';
      enabled.name = '_touched_enabled';
      enabled.value = '1';
      formEl.appendChild(enabled);

      // přidat markery jen pro pole, která se liší od výchozí hodnoty na stránce
      const inputs = formEl.querySelectorAll(':is(input, select, textarea)');
      inputs.forEach((el) => {
        if (!isDataField(el)) return;
        if (!el.name) return;
        if (!isChangedFromDefault(el)) return;
        const marker = document.createElement('input');
        marker.type = 'hidden';
        marker.name = '_touched_field';
        marker.value = el.name;
        formEl.appendChild(marker);
      });
      dirty = false;
      hideWarning();
    });

    // Varování při odchodu ze stránky
    window.addEventListener('beforeunload', function (e) {
      if (!dirty) return;
      e.preventDefault();
      e.returnValue = '';
    });
  });
})();