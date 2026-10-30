/* No OMM runtime dependency: this viewer consumes SDD metadata and extracted diagrams. */

(() => {
  'use strict';
  const config = JSON.parse(document.querySelector('#site-config').textContent);
  const english = config.language === 'en';
  const t = (ko, en) => english ? en : ko;
  const root = new URL(config.root, location.href);
  const languages = document.querySelector('.language-selector');
  if (languages) {
    languages.addEventListener('keydown', event => {
      if (event.key === 'Escape') {
        languages.open = false;
        languages.querySelector('summary').focus();
      }
    });
    document.addEventListener('click', event => {
      if (!languages.contains(event.target)) languages.open = false;
    });
    languages.addEventListener('focusout', event => {
      if (!languages.contains(event.relatedTarget)) languages.open = false;
    });
    languages.querySelectorAll('a').forEach(link => link.addEventListener('click', () => {
      const target = new URL(link.href);
      target.hash = location.hash;
      link.href = target.href;
    }));
  }
  // Share the preference across pages and editions, but not across hosted sites.
  const sidebar = document.querySelector('#sidebar');
  const layout = sidebar.parentElement;
  const desktop = window.matchMedia('(min-width: 761px)');
  const storageRoot = english ? new URL('../', root) : root;
  const widthKey = `sdd.sidebar.width:${storageRoot.pathname}`;
  const resizer = document.createElement('div');
  resizer.className = 'sidebar-resizer';
  resizer.tabIndex = 0;
  resizer.setAttribute('role', 'separator');
  resizer.setAttribute('aria-orientation', 'vertical');
  resizer.setAttribute('aria-controls', 'sidebar');
  const resizeHelp = t('메뉴 너비 조절: 드래그 또는 좌우 방향키. 두 번 클릭하면 기본 너비로 돌아갑니다.',
    'Resize menu: drag or use the left and right arrow keys. Double-click to reset.');
  resizer.setAttribute('aria-label', resizeHelp);
  resizer.title = resizeHelp;
  sidebar.after(resizer);
  const bounds = () => ({min: 180, max: Math.floor(Math.min(420, layout.clientWidth * .45))});
  function syncWidth() {
    if (!desktop.matches) return;
    const {min, max} = bounds();
    resizer.setAttribute('aria-valuemin', String(min));
    resizer.setAttribute('aria-valuemax', String(max));
    resizer.setAttribute('aria-valuenow', String(Math.round(sidebar.getBoundingClientRect().width)));
  }
  function setWidth(value) {
    const {min, max} = bounds();
    layout.style.setProperty('--preferred-sidebar-width', `${Math.max(min, Math.min(max, value))}px`);
    syncWidth();
  }
  function saveWidth() {
    try {
      const value = layout.style.getPropertyValue('--preferred-sidebar-width');
      if (value) localStorage.setItem(widthKey, String(parseFloat(value)));
      else localStorage.removeItem(widthKey);
    } catch (_) { /* Resizing still works when storage is unavailable. */ }
  }
  try {
    const saved = Number(localStorage.getItem(widthKey));
    if (Number.isFinite(saved) && saved >= 180 && saved <= 420) {
      layout.style.setProperty('--preferred-sidebar-width', `${saved}px`);
    }
  } catch (_) { /* Keep the stylesheet default. */ }
  let drag = null;
  function finishResize() {
    if (!drag) return;
    const {id} = drag;
    drag = null;
    document.body.classList.remove('resizing-sidebar');
    if (resizer.hasPointerCapture(id)) resizer.releasePointerCapture(id);
    saveWidth();
  }
  resizer.addEventListener('pointerdown', event => {
    if (!desktop.matches || event.button !== 0 || !event.isPrimary) return;
    drag = {id: event.pointerId, x: event.clientX, width: sidebar.getBoundingClientRect().width};
    resizer.setPointerCapture(event.pointerId);
    // Native pointer focus preserves the browser's keyboard-only focus ring.
    document.body.classList.add('resizing-sidebar');
  });
  resizer.addEventListener('pointermove', event => {
    if (drag && event.pointerId === drag.id) setWidth(drag.width + event.clientX - drag.x);
  });
  for (const name of ['pointerup', 'pointercancel', 'lostpointercapture']) {
    resizer.addEventListener(name, finishResize);
  }
  window.addEventListener('blur', finishResize);
  resizer.addEventListener('keydown', event => {
    if (!desktop.matches) return;
    const {min, max} = bounds();
    const width = sidebar.getBoundingClientRect().width;
    const step = event.shiftKey ? 40 : 10;
    const values = {ArrowLeft: width - step, ArrowRight: width + step, Home: min, End: max};
    if (!(event.key in values)) return;
    event.preventDefault();
    setWidth(values[event.key]);
    saveWidth();
  });
  resizer.addEventListener('dblclick', () => {
    layout.style.removeProperty('--preferred-sidebar-width');
    syncWidth();
    saveWidth();
  });
  window.addEventListener('resize', () => {
    finishResize();
    syncWidth();
  });
  syncWidth();

  // Keep navigation context within this tab, including language switches and history.
  const foldsKey = `sdd.sidebar.folds:${storageRoot.pathname}`;
  const folds = [...sidebar.querySelectorAll('details[data-nav-id]')];
  const defaults = new Map(folds.map(node => [node.dataset.navId, node.open]));
  const observed = new Map(defaults);
  const touched = new Set();
  let foldStates = new Map();
  function restoreSidebarFolds() {
    try {
      const saved = JSON.parse(sessionStorage.getItem(foldsKey));
      if (saved && saved.version === 1 && saved.states && typeof saved.states === 'object'
          && !Array.isArray(saved.states)) {
        foldStates = new Map(Object.entries(saved.states).filter(([, value]) => typeof value === 'boolean'));
      }
    } catch (_) { /* Native disclosures also work with blocked or damaged storage. */ }
    for (const node of folds) {
      const id = node.dataset.navId;
      node.open = foldStates.has(id) ? foldStates.get(id) : defaults.get(id);
      // Ignore toggle events queued by restoration, including BFCache pageshow.
      observed.set(id, node.open);
    }
  }
  function saveSidebarFolds() {
    // Scan the DOM, not the asynchronous toggle event queue. A fast navigation
    // can hide the page before toggle fires; nested states stay independent.
    for (const node of folds) {
      const id = node.dataset.navId;
      if (node.open !== observed.get(id) || touched.has(id)) foldStates.set(id, node.open);
      observed.set(id, node.open);
    }
    touched.clear();
    try {
      sessionStorage.setItem(foldsKey, JSON.stringify({version: 1, states: Object.fromEntries(foldStates)}));
    } catch (_) { /* Preserve in-memory choices and the remaining reader controls. */ }
  }
  folds.forEach(node => {
    // Native mouse and keyboard activation both click the summary. Remember
    // intent even when two quick toggles coalesce back to the default value.
    node.querySelector(':scope > summary').addEventListener('click', () => touched.add(node.dataset.navId));
    node.addEventListener('toggle', saveSidebarFolds);
  });
  const scrollKey = `sdd.sidebar.scroll:${storageRoot.pathname}`;
  function saveSidebarScroll() {
    if (!desktop.matches) return;
    try { sessionStorage.setItem(scrollKey, String(sidebar.scrollTop)); }
    catch (_) { /* Navigation remains usable when session storage is blocked. */ }
  }
  function restoreSidebarScroll() {
    if (!desktop.matches) return;
    try {
      const saved = sessionStorage.getItem(scrollKey);
      if (saved === null) return;
      const value = Number(saved);
      // The browser clamps the offset if the new page has a shorter menu.
      if (Number.isFinite(value) && value >= 0) sidebar.scrollTop = value;
    } catch (_) { /* Keep the browser's normal position. */ }
  }
  sidebar.addEventListener('click', saveSidebarScroll);
  sidebar.addEventListener('auxclick', saveSidebarScroll);
  window.addEventListener('pagehide', () => {
    saveSidebarFolds();
    saveSidebarScroll();
  });
  function restoreSidebarContext() {
    // Menu height must be final before the browser clamps its saved offset.
    restoreSidebarFolds();
    restoreSidebarScroll();
  }
  window.addEventListener('pageshow', restoreSidebarContext);
  desktop.addEventListener('change', restoreSidebarScroll);
  restoreSidebarContext();
  document.querySelectorAll('dialog [data-close]').forEach(button => {
    button.addEventListener('click', () => button.closest('dialog').close());
  });
  document.querySelectorAll('dialog').forEach(dialog => {
    const outside = event => {
      const box = dialog.getBoundingClientRect();
      return event.clientX < box.left || event.clientX > box.right
        || event.clientY < box.top || event.clientY > box.bottom;
    };
    let backdropDown = false;
    dialog.addEventListener('pointerdown', event => {
      backdropDown = event.target === dialog && outside(event);
    });
    dialog.addEventListener('click', event => {
      if (backdropDown && event.target === dialog && outside(event)) dialog.close();
      backdropDown = false;
    });
  });

  const searchDialog = document.querySelector('#search-dialog');
  const searchOpen = document.querySelector('#search-open');
  const searchInput = document.querySelector('#search-input');
  const results = document.querySelector('#search-results');
  const count = document.querySelector('#search-count');
  let index = null;
  let searchTrigger = null;
  function search() {
    if (!index) return;
    const query = searchInput.value.trim().toLocaleLowerCase();
    // A title that is the query itself (a glossary term such as "IPA (Image ...)") comes first,
    // then titles that start with it; otherwise the index order (reading order) is kept.
    const rank = item => {
      const title = item.title.toLocaleLowerCase();
      return title === query || title.startsWith(`${query} (`) || title.startsWith(`${query} ·`) ? 0
        : title.startsWith(query) ? 1 : 2;
    };
    // Glossary terms match on their own names only; otherwise "용어" would list every term
    // because they all belong to the glossary page.
    const text = item => item.url.includes('#term-') ? item.title : `${item.title} ${item.page}`;
    const matches = index.filter(item => (query || item.kind !== 'symbol')
        && text(item).toLocaleLowerCase().includes(query))
      .map((item, order) => ({item, order, rank: query ? rank(item) : 2}))
      .sort((a, b) => a.rank - b.rank || a.order - b.order).map(({item}) => item);
    results.replaceChildren();
    matches.slice(0, 100).forEach(item => {
      const li = document.createElement('li');
      const a = document.createElement('a');
      a.href = new URL(item.url, root).href;
      a.textContent = item.title;
      const small = document.createElement('small');
      const kind = item.kind === 'symbol' ? t('코드 요소', 'Symbol')
        : item.url.includes('#term-') ? t('용어', 'Term')
        : item.url.includes('#') ? t('절', 'Section') : t('문서', 'Document');
      small.textContent = kind + (item.page === item.title ? '' : ` · ${item.page}`);
      a.append(small);
      a.addEventListener('click', () => searchDialog.close());
      li.append(a);
      results.append(li);
    });
    count.textContent = t(`${matches.length}개 결과 · 문서·절·용어·코드 요소`, `${matches.length} results · Documents, sections, terms and symbols`)
      + (matches.length > 100 ? t(' · 상위 100개 표시 · 검색어를 더 입력하세요.', ' · First 100 shown · Refine your search.') : '');
  }
  async function openSearch() {
    if (document.querySelector('dialog[open]')) return;
    searchTrigger = document.activeElement;
    searchDialog.showModal();
    searchInput.focus();
    if (!index) {
      count.textContent = t('검색 목록을 읽고 있습니다.', 'Loading the search index.');
      try {
        const response = await fetch(new URL('assets/search.json', root));
        if (!response.ok) throw new Error(String(response.status));
        index = await response.json();
      } catch (_) {
        count.textContent = t('검색 목록을 읽지 못했습니다. 왼쪽 문서 메뉴를 이용하세요.', 'Could not load the search index. Use the documentation menu.');
        return;
      }
    }
    search();
  }
  searchOpen.hidden = false;
  searchOpen.addEventListener('click', openSearch);
  searchInput.addEventListener('input', search);
  searchInput.addEventListener('keydown', event => {
    if (event.key === 'ArrowDown') { event.preventDefault(); results.querySelector('a')?.focus(); }
    if (event.key === 'Enter') results.querySelector('a')?.click();
  });
  searchDialog.addEventListener('close', () => searchTrigger?.focus());
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      const opened = document.querySelector('dialog[open]');
      if (opened) { event.preventDefault(); opened.close(); }
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault(); openSearch();
    }
  });

  const diagramDialog = document.querySelector('#diagram-dialog');
  const viewport = document.querySelector('#diagram-viewport');
  const canvas = document.querySelector('#diagram-canvas');
  const nodeInput = document.querySelector('#node-search');
  let active = null;
  function scale(value, center = true) {
    if (!active) return;
    const old = active.scale;
    const x = (viewport.scrollLeft + viewport.clientWidth / 2) / old;
    const y = (viewport.scrollTop + viewport.clientHeight / 2) / old;
    active.scale = Math.max(.05, Math.min(8, value));
    active.svg.style.width = `${active.width * active.scale}px`;
    active.svg.style.height = `${active.height * active.scale}px`;
    document.querySelector('#zoom-value').textContent = `${Math.round(active.scale * 100)}%`;
    if (center) {
      viewport.scrollLeft = x * active.scale - viewport.clientWidth / 2;
      viewport.scrollTop = y * active.scale - viewport.clientHeight / 2;
    }
  }
  function fit() {
    if (!active) return;
    scale(Math.min((viewport.clientWidth - 60) / active.width, (viewport.clientHeight - 60) / active.height, 1), false);
    viewport.scrollTo(0, 0);
  }
  function searchNodes() {
    if (!active) return;
    const query = nodeInput.value.trim().toLowerCase();
    let total = 0;
    let first = null;
    active.svg.querySelectorAll('.node, .actor, .classGroup').forEach(node => {
      const matches = !!query && node.textContent.toLowerCase().includes(query);
      node.classList.toggle('is-match', matches);
      if (matches) { total++; first ||= node; }
    });
    document.querySelector('#node-count').textContent = query ? t(`${total}개 일치`, `${total} matches`) : '';
    if (first) first.scrollIntoView({block: 'nearest', inline: 'nearest'});
  }
  function openDiagram(trigger) {
    const svg = trigger.querySelector('svg');
    if (!svg) return;
    const box = svg.viewBox.baseVal;
    const placeholder = document.createComment('diagram position');
    svg.before(placeholder);
    active = {svg, trigger, placeholder, style: svg.getAttribute('style'), scale: 1,
      width: box.width || svg.getBoundingClientRect().width,
      height: box.height || svg.getBoundingClientRect().height};
    canvas.append(svg);
    nodeInput.value = '';
    document.querySelector('#node-count').textContent = '';
    document.querySelector('#diagram-title').textContent = trigger.getAttribute('data-title') || t('다이어그램', 'Diagram');
    diagramDialog.showModal();
    fit();
    if (window.matchMedia('(max-width: 760px)').matches && active.scale < .85) {
      scale(.85, false);
      viewport.scrollTo(0, 0);
    }
    nodeInput.focus();
  }
  diagramDialog.addEventListener('close', () => {
    if (!active) return;
    active.svg.querySelectorAll('.is-match').forEach(node => node.classList.remove('is-match'));
    if (active.style === null) active.svg.removeAttribute('style');
    else active.svg.setAttribute('style', active.style);
    active.placeholder.replaceWith(active.svg);
    active.trigger.focus({preventScroll: true});
    active = null;
  });
  nodeInput.addEventListener('input', searchNodes);
  document.querySelector('#zoom-in').addEventListener('click', () => active && scale(active.scale * 1.25));
  document.querySelector('#zoom-out').addEventListener('click', () => active && scale(active.scale / 1.25));
  document.querySelector('#zoom-reset').addEventListener('click', () => scale(1));
  document.querySelector('#zoom-fit').addEventListener('click', fit);
  window.addEventListener('resize', () => { if (active) fit(); });

  const diagrams = [...document.querySelectorAll('.mermaid')];
  if (diagrams.length) {
    import(new URL(config.mermaid, root).href).then(async ({default: mermaid}) => {
      mermaid.initialize({startOnLoad: false, securityLevel: 'strict', theme: 'base',
        themeVariables: {background: '#ffffff', primaryColor: '#edf5f1', primaryTextColor: '#17201e',
          primaryBorderColor: '#8ba99e', lineColor: '#66766f', secondaryColor: '#f6f7f8',
          tertiaryColor: '#ffffff', edgeLabelBackground: '#ffffff',
          fontFamily: 'Geist, Malgun Gothic, system-ui, sans-serif', fontSize: '14px'},
        flowchart: {htmlLabels: false, curve: 'basis', nodeSpacing: 38, rankSpacing: 65, padding: 16}});
      for (const [i, diagram] of diagrams.entries()) {
        const source = diagram.textContent;
        try {
          const {svg, bindFunctions} = await mermaid.render(`sdd-diagram-${i}`, source);
          diagram.innerHTML = svg;
          bindFunctions?.(diagram);
          diagram.dataset.ready = 'true';
          let heading = diagram.previousElementSibling;
          while (heading && !/^H[1-6]$/.test(heading.tagName)) heading = heading.previousElementSibling;
          diagram.dataset.title = heading?.textContent || t('다이어그램', 'Diagram');
          diagram.tabIndex = 0;
          diagram.setAttribute('role', 'button');
          diagram.setAttribute('aria-label', t('다이어그램 확대', 'Enlarge diagram'));
          diagram.setAttribute('aria-haspopup', 'dialog');
          diagram.addEventListener('click', () => openDiagram(diagram));
          diagram.addEventListener('keydown', event => {
            if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openDiagram(diagram); }
          });
          const hint = document.createElement('p');
          hint.className = 'diagram-hint';
          hint.textContent = t('그림을 누르면 확대하고 요소를 검색할 수 있습니다.', 'Click the diagram to enlarge it and search its elements.');
          diagram.after(hint);
        } catch (_) {
          diagram.textContent = source;
          diagram.classList.add('diagram-error');
          diagram.before(Object.assign(document.createElement('p'), {textContent: t('그림을 그리지 못했습니다. 아래 Mermaid 원문을 확인하세요.', 'Could not render the diagram. See the Mermaid source below.')}));
        }
      }
    }).catch(() => {
      diagrams.forEach(diagram => {
        diagram.before(Object.assign(document.createElement('p'), {className: 'diagram-error',
          textContent: t('Mermaid를 불러오지 못해 원문을 표시합니다. 사내망에서는 로컬 Mermaid 경로를 설정하세요.', 'Could not load Mermaid; showing the source. Configure a local Mermaid path for an internal network.')}));
      });
    });
  }

  /* Terms: underline the first use of each glossary term in the article and show its meaning
     in place. The HTML stays unchanged, so pages and translations keep their source hashes;
     without JavaScript the folded term list and the glossary page still work. */
  const article = document.querySelector('article');
  if (config.terms && article) {
    const SKIP = 'code, pre, a, h1, h2, h3, h4, h5, h6, summary, details, .mermaid, button, script, style';
    const escape = value => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    let popover = null;
    let current = null;
    let pinned = false;
    let hideTimer = 0;
    function hide(restoreFocus) {
      clearTimeout(hideTimer);
      if (!popover || popover.hidden) return;
      popover.hidden = true;
      current?.setAttribute('aria-expanded', 'false');
      if (restoreFocus) current?.focus();
      current = null;
      pinned = false;
    }
    function show(button, pin, fromKeyboard) {
      clearTimeout(hideTimer);
      const item = button.term;
      if (!popover) {
        popover = document.createElement('div');
        popover.id = 'term-popover';
        popover.setAttribute('role', 'dialog');
        popover.tabIndex = -1;
        popover.hidden = true;
        popover.addEventListener('mouseenter', () => clearTimeout(hideTimer));
        popover.addEventListener('mouseleave', () => { if (!pinned) hideTimer = setTimeout(() => hide(false), 200); });
        document.body.append(popover);
      }
      if (current && current !== button) current.setAttribute('aria-expanded', 'false');
      current = button;
      pinned = pin || pinned;
      const title = Object.assign(document.createElement('strong'), {textContent: item.term});
      const text = Object.assign(document.createElement('p'), {textContent: item.definition});
      const more = Object.assign(document.createElement('a'), {
        href: new URL(`glossary.html#${encodeURIComponent(item.id)}`, root).href,
        textContent: t('용어집에서 보기', 'Open in glossary')});
      popover.replaceChildren(title, text, more);
      popover.setAttribute('aria-label', item.term);
      popover.hidden = false;
      button.setAttribute('aria-expanded', 'true');
      const box = button.getBoundingClientRect();
      const width = Math.min(360, document.documentElement.clientWidth - 32);
      popover.style.width = `${width}px`;
      popover.style.left = `${Math.max(16, Math.min(box.left, document.documentElement.clientWidth - width - 16)) + scrollX}px`;
      // Open below the term; near the bottom of a phone screen, open above it instead.
      const height = popover.offsetHeight;
      const above = box.bottom + 8 + height > innerHeight && box.top - 8 - height >= 0;
      popover.style.top = `${(above ? box.top - 8 - height : box.bottom + 8) + scrollY}px`;
      // From the keyboard, move focus into the box so its glossary link is the next Tab stop.
      if (fromKeyboard) popover.focus();
    }
    // The URL carries the data's hash, so a new deploy never shows cached definitions.
    fetch(new URL(`assets/glossary.json?v=${encodeURIComponent(config.terms)}`, root)).then(response => response.ok ? response.json() : []).then(items => {
      const names = items.flatMap(item => item.names.map(name => ({item, name})))
        .sort((a, b) => b.name.length - a.name.length);
      if (!names.length) return;
      // Acronyms match exactly; other names ignore case. The boundaries are the ones the generator
      // uses to find terms (glossary.py BEFORE/AFTER): only ASCII letters and digits are word
      // characters, so "IPA는" and "LSC-보정" match while "file.IPA" and "Mali-C55" do not.
      const pattern = new RegExp(names.map(({name}) => {
        const exact = name === name.toUpperCase();
        const body = exact ? escape(name) : escape(name).replace(/[A-Za-z]/g, c => `[${c.toLowerCase()}${c.toUpperCase()}]`);
        return `(?<![A-Za-z0-9_.])(?<![A-Za-z0-9]-)${body}(?![A-Za-z0-9_]|-[A-Za-z0-9])`;
      }).join('|'), 'g');
      const lookup = new Map(names.map(({item, name}) => [name.toLowerCase(), item]));
      const seen = new Set();
      const walker = document.createTreeWalker(article, NodeFilter.SHOW_TEXT, {
        acceptNode: node => node.parentElement.closest(SKIP) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT});
      const nodes = [];
      while (walker.nextNode()) nodes.push(walker.currentNode);
      for (let node of nodes) {
        pattern.lastIndex = 0;
        let match;
        while ((match = pattern.exec(node.data))) {
          const item = lookup.get(match[0].toLowerCase());
          if (!item || seen.has(item.id)) continue;
          seen.add(item.id);
          const rest = node.splitText(match.index);
          node = rest.splitText(match[0].length);
          const button = Object.assign(document.createElement('button'), {type: 'button', className: 'term', textContent: rest.data});
          button.term = item;
          button.setAttribute('aria-expanded', 'false');
          button.setAttribute('aria-controls', 'term-popover');
          button.addEventListener('click', event => {
            // event.detail is 0 for Enter/Space activation.
            if (current === button && pinned) hide(false); else show(button, true, event.detail === 0);
          });
          button.addEventListener('mouseenter', () => { if (matchMedia('(hover: hover)').matches && !pinned) show(button, false); });
          button.addEventListener('mouseleave', () => { if (!pinned) hideTimer = setTimeout(() => hide(false), 200); });
          rest.replaceWith(button);
          pattern.lastIndex = 0;
        }
      }
    }).catch(error => {
      // Older browsers without regex lookbehind land here; the folded list and glossary still work.
      console.warn('Glossary term highlighting is unavailable:', error);
    });
    // pointerdown also fires for taps on plain text in iOS Safari, where click on document may not.
    document.addEventListener('pointerdown', event => {
      if (popover && !popover.contains(event.target) && !event.target.closest?.('button.term')) hide(false);
    });
    document.addEventListener('keydown', event => { if (event.key === 'Escape' && popover && !popover.hidden) hide(true); });
  }
})();
