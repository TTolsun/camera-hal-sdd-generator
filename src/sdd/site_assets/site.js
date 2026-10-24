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
  document.body.classList.add('js');
  const menu = document.querySelector('#menu-toggle');
  menu.hidden = false;
  menu.addEventListener('click', () => {
    const open = document.querySelector('#sidebar').classList.toggle('is-open');
    menu.setAttribute('aria-expanded', String(open));
  });
  document.querySelectorAll('dialog [data-close]').forEach(button => {
    button.addEventListener('click', () => button.closest('dialog').close());
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
    const matches = index.filter(item => text(item).toLocaleLowerCase().includes(query))
      .map((item, order) => ({item, order, rank: query ? rank(item) : 2}))
      .sort((a, b) => a.rank - b.rank || a.order - b.order).map(({item}) => item);
    results.replaceChildren();
    matches.forEach(item => {
      const li = document.createElement('li');
      const a = document.createElement('a');
      a.href = new URL(item.url, root).href;
      a.textContent = item.title;
      const small = document.createElement('small');
      small.textContent = item.page;
      a.append(small);
      a.addEventListener('click', () => searchDialog.close());
      li.append(a);
      results.append(li);
    });
    count.textContent = t(`${matches.length}개 결과 · 문서 제목, 절 제목과 용어를 검색합니다.`, `${matches.length} results · Searching document titles, section titles and terms.`);
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
