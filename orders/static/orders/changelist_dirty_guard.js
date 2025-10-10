// filepath: /home/zpilat/Python/Django_order_processing/orders/static/orders/changelist_dirty_guard.js
/* global django */
(function () {
  const $ = (window.django && window.django.jQuery) || window.jQuery;
  if (!$) return;

  const formSel = '#changelist-form';
  let dirty = false;

  function ensureWarning() {
    const content = document.getElementById('content') || document.body;

    // Najdi nebo vytvoř UL.messagelist
    let list = content.querySelector('ul.messagelist');
    if (!list) {
      list = document.createElement('ul');
      list.className = 'messagelist';
      content.insertBefore(list, content.firstChild);
    }

    // Najdi nebo vytvoř naše LI.warning
    let item = document.getElementById('dirty-warning');
    if (!item) {
      item = document.createElement('li');
      item.id = 'dirty-warning';
      item.className = 'warning';
      item.textContent = 'Máte neuložené změny. Nezapomeňte uložit.';
      item.style.display = 'none';
      list.appendChild(item);
    }
    return item;
  }

  function showWarning() {
    const item = ensureWarning();
    item.style.display = 'list-item';
  }

  function hideWarning() {
    const item = document.getElementById('dirty-warning');
    if (item) item.style.display = 'none';
  }

  $(function () {
    const $form = $(formSel);
    if ($form.length === 0) return;

    // Označit “dirty” při změně libovolného vstupu v changelistu
    $(document).on('change input', formSel + ' :input', function () {
      dirty = true;
      showWarning();
    });

    // Při odeslání formuláře zrušit varování
    $(document).on('submit', formSel, function () {
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