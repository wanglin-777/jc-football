(function () {
  'use strict';
  var grid = document.getElementById('match-grid');
  if (!grid) return;
  var cards = Array.from(grid.querySelectorAll('.match-card'));
  var query = document.getElementById('match-search');
  var league = document.getElementById('match-league');
  var risk = document.getElementById('match-risk');
  var sort = document.getElementById('match-sort');
  function apply() {
    var term = query.value.trim().toLocaleLowerCase();
    var count = 0;
    cards.sort(function (a, b) {
      return sort.value === 'prob'
        ? Number(b.dataset.prob) - Number(a.dataset.prob) || Number(a.dataset.index) - Number(b.dataset.index)
        : Number(a.dataset.index) - Number(b.dataset.index);
    });
    cards.forEach(function (card) {
      card.hidden = !(card.dataset.search.toLocaleLowerCase().includes(term)
        && (!league.value || card.dataset.league === league.value)
        && (!risk.value || card.dataset.risk === risk.value));
      if (!card.hidden) count++;
      grid.appendChild(card);
    });
    document.getElementById('match-count').textContent = count + ' / ' + cards.length + ' 场比赛';
    document.getElementById('match-empty').hidden = count !== 0;
  }
  query.addEventListener('input', apply);
  [league, risk, sort].forEach(function (control) { control.addEventListener('change', apply); });
  document.getElementById('match-reset').addEventListener('click', function () {
    query.value = league.value = risk.value = ''; sort.value = 'index'; apply(); query.focus();
  });
  var tabs = Array.from(document.querySelectorAll('.main-tabs [data-tab]'));
  tabs.forEach(function (button, index) {
    button.setAttribute('role', 'tab');
    button.id = 'nav-' + button.dataset.tab;
    button.setAttribute('aria-controls', 'tab-' + button.dataset.tab);
    var panel = document.getElementById('tab-' + button.dataset.tab);
    panel.setAttribute('role', 'tabpanel');
    panel.setAttribute('aria-labelledby', button.id);
    button.addEventListener('keydown', function (event) {
      var target;
      if (event.key === 'ArrowRight') target = (index + 1) % tabs.length;
      if (event.key === 'ArrowLeft') target = (index + tabs.length - 1) % tabs.length;
      if (event.key === 'Home') target = 0;
      if (event.key === 'End') target = tabs.length - 1;
      if (target !== undefined) { event.preventDefault(); tabs[target].click(); tabs[target].focus(); }
    });
  });
  showTab('combo');
  apply();
})();
