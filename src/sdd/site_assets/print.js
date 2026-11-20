/* Whole-document copy: draw every diagram first, then allow printing (Save as PDF).
   Printing before the diagrams are drawn would put Mermaid source text in the PDF. */
(() => {
  'use strict';
  const config = JSON.parse(document.querySelector('#site-config').textContent);
  const english = config.language === 'en';
  const t = (ko, en) => english ? en : ko;
  const root = new URL(config.root, location.href);
  const button = document.querySelector('#print-document');
  const status = document.querySelector('#print-status');
  const diagrams = [...document.querySelectorAll('.mermaid')];
  button.addEventListener('click', () => window.print());

  function finish(failed) {
    button.disabled = false;
    status.textContent = failed
      ? t(`그림 ${failed}개를 그리지 못해 Mermaid 원문으로 표시합니다. 원문도 PDF에 포함됩니다.`,
          `${failed} diagram(s) could not be drawn and are shown as Mermaid source, which the PDF includes.`)
      : t(`인쇄 준비가 끝났습니다. 그림 ${diagrams.length}개를 모두 그렸습니다.`,
          `Ready to print. All ${diagrams.length} diagram(s) are drawn.`);
    // The site's download menu opens this page with ?print to go straight to the print dialog.
    if (new URLSearchParams(location.search).has('print')) window.print();
  }

  if (!diagrams.length) { finish(0); return; }
  import(new URL(config.mermaid, root).href).then(async ({default: mermaid}) => {
    // Same appearance as the site pages (site.js).
    mermaid.initialize({startOnLoad: false, securityLevel: 'strict', theme: 'base',
      themeVariables: {background: '#ffffff', primaryColor: '#edf5f1', primaryTextColor: '#17201e',
        primaryBorderColor: '#8ba99e', lineColor: '#66766f', secondaryColor: '#f6f7f8',
        tertiaryColor: '#ffffff', edgeLabelBackground: '#ffffff',
        fontFamily: 'Geist, Malgun Gothic, system-ui, sans-serif', fontSize: '14px'},
      flowchart: {htmlLabels: false, curve: 'basis', nodeSpacing: 38, rankSpacing: 65, padding: 16}});
    let failed = 0;
    for (const [i, diagram] of diagrams.entries()) {
      status.textContent = t(`그림을 그리는 중입니다 (${i + 1}/${diagrams.length}).`,
                             `Drawing diagrams (${i + 1}/${diagrams.length}).`);
      const source = diagram.textContent;
      try {
        const {svg} = await mermaid.render(`sdd-print-${i}`, source);
        diagram.innerHTML = svg;
        diagram.dataset.ready = 'true';
      } catch (_) {
        failed += 1;
        diagram.textContent = source;
        diagram.classList.add('diagram-error');
      }
    }
    finish(failed);
  }).catch(() => finish(diagrams.length));
})();
