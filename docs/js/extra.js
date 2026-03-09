// In-page filter for abbreviation lists (<dl class="abbr-list">)
(function() {
  function normalize(s) {
    return s
      .normalize('NFD')                // rozložit znaky s diakritikou
      .replace(/[\u0300-\u036f]/g, '') // odstranit diakritiku
      .toLowerCase();
  }

  function setupFilter() {
    const input = document.getElementById('abbrev-filter');
    if (!input) return;

    const dls = document.querySelectorAll('dl.abbr-list');
    if (!dls.length) return;

    input.addEventListener('input', () => {
      const q = normalize(input.value || '');
      const showAll = q.length === 0;

      dls.forEach(dl => {
        const pairs = dl.querySelectorAll('dt');
        pairs.forEach(dt => {
          const dd = dt.nextElementSibling;
          const text = normalize(dt.textContent + ' ' + (dd ? dd.textContent : ''));
          const match = showAll || text.includes(q);
          dt.style.display = match ? '' : 'none';
          if (dd) dd.style.display = match ? '' : 'none';
        });
      });
    });
  }


  // Re-attach filter when MkDocs Material navigates to a new page
  function initWhenReady() {
    setupFilter();
    document.addEventListener('DOMContentLoaded', setupFilter);
    document.addEventListener('readystatechange', () => {
      if (document.readyState === 'complete') setupFilter();
    });
    if (document.body && window.document$) {
      window.document$.subscribe(setupFilter); // Material's event for page change
    }
  }

  initWhenReady();
})();

