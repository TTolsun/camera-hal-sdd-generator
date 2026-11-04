/* Progressive reader controls. Manuscripts, source pins and review states stay intact. */
(() => {
  'use strict';
  const config = JSON.parse(document.querySelector('#site-config').textContent);
  const english = config.language === 'en';
  const t = (ko, en) => english ? en : ko;
  const header = document.querySelector('.site-header');
  const updateHeader = () => document.documentElement.style.setProperty('--site-header-height', `${header.getBoundingClientRect().height}px`);
  updateHeader();
  if (typeof ResizeObserver !== 'undefined') new ResizeObserver(updateHeader).observe(header);
  window.addEventListener('resize', updateHeader);

  const menu = document.querySelector('#menu-toggle');
  const sidebar = document.querySelector('#sidebar');
  const mobile = window.matchMedia('(max-width: 760px)');
  const backdrop = document.createElement('button');
  backdrop.className = 'menu-backdrop';
  backdrop.type = 'button';
  backdrop.tabIndex = -1;
  backdrop.setAttribute('aria-label', t('메뉴 닫기', 'Close menu'));
  backdrop.hidden = true;
  sidebar.before(backdrop);
  const closeMenu = document.createElement('button');
  closeMenu.className = 'sidebar-close';
  closeMenu.type = 'button';
  closeMenu.textContent = t('메뉴 닫기', 'Close menu');
  closeMenu.hidden = true;
  sidebar.prepend(closeMenu);
  const backgrounds = [document.querySelector('main'), document.querySelector('.page-toc'),
    document.querySelector('.brand'), document.querySelector('#search-open'), document.querySelector('.language-selector')].filter(Boolean);
  let inertBefore = [];
  let menuOpen = false;
  let menuScroll = null;
  function visibleMenuTarget(node) {
    // A summary remains visible in its own closed details. Each outer closed
    // ancestor replaces the target so we never focus a hidden descendant.
    for (let parent = node.parentElement; parent && parent !== sidebar; parent = parent.parentElement) {
      if (parent.matches('details:not([open])')) node = parent.querySelector(':scope > summary');
    }
    return node;
  }
  function setMenu(open, restore = true) {
    open = open && mobile.matches;
    if (open === menuOpen) return;
    if (open) menuScroll = {x: scrollX, y: scrollY};
    menuOpen = open;
    sidebar.classList.toggle('is-open', open);
    document.documentElement.classList.toggle('menu-open', open);
    menu.setAttribute('aria-expanded', String(open));
    backdrop.hidden = closeMenu.hidden = !open;
    if (open) {
      inertBefore = backgrounds.map(node => node.inert);
      backgrounds.forEach(node => { node.inert = true; });
      const language = document.querySelector('.language-selector');
      if (language) language.open = false;
      sidebar.setAttribute('role', 'dialog');
      sidebar.setAttribute('aria-modal', 'true');
      sidebar.setAttribute('aria-label', t('문서 메뉴', 'Documentation menu'));
      // The current link may be inside several user-closed disclosures. Focus
      // the outermost closed ancestor's visible summary without reopening it.
      const activeLink = visibleMenuTarget(sidebar.querySelector('a[aria-current="page"]') || closeMenu);
      activeLink.focus({preventScroll: true});
      const target = activeLink.getBoundingClientRect(), box = sidebar.getBoundingClientRect();
      if (target.top < box.top || target.bottom > box.bottom) {
        sidebar.scrollTop += target.top - box.top - sidebar.clientHeight / 2;
      }
    } else {
      backgrounds.forEach((node, i) => { node.inert = inertBefore[i]; });
      sidebar.removeAttribute('role');
      sidebar.removeAttribute('aria-modal');
      sidebar.removeAttribute('aria-label');
      if (restore) menu.focus({preventScroll: true});
      if (restore && menuScroll) window.scrollTo({left: menuScroll.x, top: menuScroll.y, behavior: 'instant'});
    }
  }
  menu.hidden = false;
  document.body.classList.add('js');
  menu.addEventListener('click', () => setMenu(!menuOpen));
  closeMenu.addEventListener('click', () => setMenu(false));
  backdrop.addEventListener('click', () => setMenu(false));
  sidebar.addEventListener('click', event => {
    if (event.target.closest('a[href]')) setMenu(false, false);
  });
  mobile.addEventListener('change', () => { if (!mobile.matches) setMenu(false, false); });
  document.addEventListener('keydown', event => {
    if (!menuOpen) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      setMenu(false);
    } else if (event.key === 'Tab') {
      const focusable = [...sidebar.querySelectorAll('a[href],button,summary,[tabindex="0"]')]
        .filter(node => node.getClientRects().length && !node.disabled && visibleMenuTarget(node) === node);
      const first = focusable[0], last = focusable.at(-1);
      if (!sidebar.contains(document.activeElement) || (event.shiftKey && document.activeElement === first)) {
        event.preventDefault();
        (event.shiftKey ? last : first)?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    }
  });

  let origin = null;
  let returnFrame = null;
  let originNumber = 0;
  function clearEvidenceOrigin() {
    if (origin) history.scrollRestoration = origin.restoration;
    origin = null;
    cancelAnimationFrame(returnFrame);
    document.querySelectorAll('.evidence-return').forEach(button => button.remove());
  }
  function restoreExplanation() {
    if (!origin || !origin.link.isConnected) return;
    history.scrollRestoration = origin.restoration;
    cancelAnimationFrame(returnFrame);
    const returning = origin;
    returnFrame = requestAnimationFrame(() => {
      if (origin !== returning) return;
      returning.link.focus({preventScroll: true});
      window.scrollTo({left: returning.x, top: returning.y, behavior: 'instant'});
    });
  }
  function revealEvidence() {
    const id = location.hash.slice(1);
    if (!/^source-[0-9a-f]{16}$/.test(id)) return;
    const target = document.getElementById(id);
    const anchor = target?.parentElement?.tagName === 'P' ? target.parentElement : target;
    const panel = anchor?.nextElementSibling;
    if (panel?.tagName !== 'DETAILS') return;
    for (let parent = panel.parentElement; parent; parent = parent.parentElement) {
      if (parent.tagName === 'DETAILS') parent.open = true;
    }
    panel.open = true;
    if (origin) {
      history.scrollRestoration = 'manual';
      if (location.href !== origin.url) {
        const state = {...history.state};
        delete state.sddEvidenceReturn;
        history.replaceState(state, '', location.href);
      }
      let button = panel.querySelector(':scope > .evidence-return');
      if (!button) {
        button = document.createElement('button');
        button.type = 'button';
        button.className = 'evidence-return';
        button.textContent = t('설명으로 돌아가기', 'Back to explanation');
        panel.querySelector('summary').after(button);
        button.addEventListener('click', () => {
          if (!origin) return;
          history.pushState({sddEvidenceReturn: origin.token}, '', origin.url);
          restoreExplanation();
        });
      }
    }
    panel.querySelector('summary')?.focus({preventScroll: true});
    panel.scrollIntoView({block: 'start'});
  }
  function evidenceLocation() {
    if (origin && location.href !== origin.url && location.href !== origin.targetUrl) clearEvidenceOrigin();
    if (origin && location.href === origin.url && history.state?.sddEvidenceReturn === origin.token) {
      restoreExplanation();
    } else {
      revealEvidence();
      if (origin && !/^#source-[0-9a-f]{16}$/.test(location.hash)) history.scrollRestoration = origin.restoration;
    }
  }
  document.addEventListener('click', event => {
    const link = event.target.closest('a[href^="#source-"]');
    if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    if (!link) {
      if (origin && event.target.closest('a[href]')) clearEvidenceOrigin();
      return;
    }
    document.querySelectorAll('.evidence-return').forEach(button => button.remove());
    origin = {link, url: location.href, targetUrl: link.href, x: scrollX, y: scrollY,
      token: ++originNumber, restoration: origin?.restoration ?? history.scrollRestoration};
    history.replaceState({...history.state, sddEvidenceReturn: origin.token}, '', location.href);
    history.scrollRestoration = 'manual';
    if (link.hash === location.hash) {
      event.preventDefault();
      history.pushState({}, '', link.href);
      revealEvidence();
    }
  });
  for (const event of ['hashchange', 'popstate', 'pageshow']) window.addEventListener(event, evidenceLocation);
  window.addEventListener('pagehide', clearEvidenceOrigin);
  evidenceLocation();

  if (!config.index) return;
  const article = document.querySelector('article');
  const packages = [];
  let group = null;
  let heading = null;
  for (const child of article.children) {
    if (child.tagName === 'H2') {
      group = {name: child.textContent.trim(), heading: child, tables: []};
      packages.push(group);
      heading = child;
    } else if (child.tagName === 'H3') heading = child;
    else if (group && child.matches('.table-scroll') && child.querySelector('tr[data-symbol-kind]')) {
      group.tables.push({element: child, heading, rows: [...child.querySelectorAll('tr[data-symbol-kind]')]});
    }
  }
  const groups = packages.filter(item => item.tables.length);
  const rows = groups.flatMap(item => item.tables.flatMap(table => table.rows));
  if (!rows.length) return;
  const form = document.createElement('form');
  form.className = 'index-tools';
  form.setAttribute('role', 'search');
  form.setAttribute('aria-label', t('코드 색인 검색', 'Search the code index'));
  function field(label, node, id) {
    const wrapper = document.createElement('label');
    wrapper.htmlFor = node.id = id;
    const text = document.createElement('span');
    text.textContent = label;
    wrapper.append(text, node);
    form.append(wrapper);
  }
  const query = document.createElement('input');
  query.type = 'search';
  query.placeholder = t('클래스·함수·경로', 'Class, function or path');
  field(t('색인에서 찾기', 'Search this index'), query, 'index-query');
  const packageSelect = document.createElement('select');
  packageSelect.add(new Option(t('모든 패키지', 'All packages'), ''));
  groups.forEach(item => packageSelect.add(new Option(item.name, item.name)));
  field(t('패키지', 'Package'), packageSelect, 'index-package');
  const typeSelect = document.createElement('select');
  for (const [value, name] of [['', t('모든 종류', 'All kinds')], ['class', t('클래스', 'Class')], ['function', t('함수', 'Function')]]) {
    typeSelect.add(new Option(name, value));
  }
  field(t('종류', 'Kind'), typeSelect, 'index-kind');
  const clear = document.createElement('button');
  clear.type = 'button';
  clear.textContent = t('필터 지우기', 'Clear filters');
  const status = document.createElement('p');
  status.id = 'index-count';
  status.setAttribute('role', 'status');
  form.append(clear, status);
  (article.querySelector(':scope > p') || article.firstElementChild).after(form);
  const texts = new Map(rows.map(row => [row, row.textContent.normalize('NFC').toLocaleLowerCase()]));
  function filter() {
    const term = query.value.trim().normalize('NFC').toLocaleLowerCase();
    let total = 0;
    groups.forEach(item => {
      let packageTotal = 0;
      const headingCounts = new Map();
      item.tables.forEach(table => {
        let count = 0;
        table.rows.forEach(row => {
          row.hidden = !!((packageSelect.value && packageSelect.value !== item.name)
            || (typeSelect.value && typeSelect.value !== row.dataset.symbolKind) || !texts.get(row).includes(term));
          if (!row.hidden) count++;
        });
        table.element.hidden = count === 0;
        if (table.heading !== item.heading) headingCounts.set(table.heading, (headingCounts.get(table.heading) || 0) + count);
        packageTotal += count;
      });
      headingCounts.forEach((count, heading) => { heading.hidden = count === 0; });
      item.heading.hidden = packageTotal === 0;
      total += packageTotal;
    });
    status.textContent = t(`${total} / ${rows.length}개 항목`, `${total} of ${rows.length} entries`);
  }
  function reset() { query.value = packageSelect.value = typeSelect.value = ''; filter(); }
  form.addEventListener('submit', event => event.preventDefault());
  query.addEventListener('input', filter);
  packageSelect.addEventListener('change', filter);
  typeSelect.addEventListener('change', filter);
  clear.addEventListener('click', () => { reset(); query.focus(); });
  function revealSymbol() {
    if (!/^#symbol-[0-9a-f]{16}(?:-\d+)?$/.test(location.hash)) return;
    const row = document.getElementById(location.hash.slice(1));
    if (!row) return;
    reset();
    requestAnimationFrame(() => { row.focus({preventScroll: true}); row.scrollIntoView({block: 'center'}); });
  }
  window.addEventListener('hashchange', revealSymbol);
  document.addEventListener('click', event => {
    const link = event.target.closest('a[href]');
    if (link && link.pathname === location.pathname && link.hash === location.hash) revealSymbol();
  });
  filter();
  revealSymbol();
})();
