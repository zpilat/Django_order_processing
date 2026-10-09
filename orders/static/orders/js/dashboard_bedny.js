(() => {
  const content = document.getElementById('dashboard-content');
  if (!content) return;

  let expanded = false;
  let grid = null;
  let frame = null;
  let observedWidth = null;
  const observer = new ResizeObserver(entries => {
    const width = entries[0].contentRect.width;
    if (width !== observedWidth) {
      observedWidth = width;
      scheduleAlignment();
    }
  });

  function alignCards() {
    frame = null;
    if (!grid) return;

    // Measure natural heights first, then give every card the same sections.
    const sections = [
      ['.dashboard-customer-header', '--dashboard-card-header-height'],
      ['.dashboard-customer-body', '--dashboard-card-body-height'],
      ['.dashboard-details > h4', '--dashboard-card-details-title-height'],
      ['.dashboard-details', '--dashboard-card-details-height'],
    ];
    sections.forEach(([, variable]) => grid.style.setProperty(variable, '0px'));
    sections.forEach(([selector, variable]) => {
      const height = Math.ceil(Math.max(
        0, ...Array.from(grid.querySelectorAll(selector), element => element.getBoundingClientRect().height),
      ));
      grid.style.setProperty(variable, `${height}px`);
    });
  }

  function scheduleAlignment() {
    if (frame === null) frame = requestAnimationFrame(alignCards);
  }

  function updateDetails() {
    content.querySelectorAll('.dashboard-details').forEach(detail => { detail.hidden = !expanded; });
    const button = content.querySelector('#dashboard-details-toggle');
    if (button) {
      button.setAttribute('aria-expanded', String(expanded));
      button.textContent = expanded ? 'Sbalit detaily' : 'Rozbalit detaily';
    }
    scheduleAlignment();
  }

  function initialize() {
    observer.disconnect();
    observedWidth = null;
    grid = content.querySelector('.dashboard-customer-grid');
    if (grid) observer.observe(grid);
    updateDetails();
  }

  content.addEventListener('click', event => {
    if (!event.target.closest('#dashboard-details-toggle')) return;
    expanded = !expanded;
    updateDetails();
  });

  content.addEventListener('htmx:afterSwap', event => {
    if (event.detail.target === content) initialize();
  });
  document.fonts.ready.then(scheduleAlignment);
  initialize();
})();
