const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const {chromium} = require(path.resolve('build/issue252/browser-deps/node_modules/playwright'));
const base = process.argv[2];
const out = path.resolve(process.argv[3]);
const ids = ['preparation-depth-flow','uvc-depth-flow','callback-order-flow','callback-depth-flow','queued-lifetime-flow','stop-depth-flow','change-verification-flow','callback-boundaries-flow','failure-investigation-flow','submission-order-flow','stop-lifetime-flow','fence-timer-order-flow','request-ownership','pre-qbuf-failure-flow'];
if (!/^https?:\/\//.test(base)) throw Error('Supply an exact local or public site URL');

(async () => {
  await fs.mkdir(out,{recursive:false});
  const browser = await chromium.launch({channel:'chrome',headless:true});
  const report = {schema:1,base,runs:[],scope:'Selected bilingual request path; fresh isolated Chromium contexts, not a physical camera/phone or human reader evaluation.'};
  try {
    const response = await (await browser.newContext()).request.get(new URL('site-manifest.json',base).href);
    assert.ok(response.ok());
    report.build_id = (await response.json()).build_id;
    for (const mobile of [false,true]) for (const language of ['ko','en']) {
      const context = await browser.newContext({viewport:mobile?{width:390,height:844}:{width:1440,height:1000},isMobile:mobile,hasTouch:mobile});
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror',error=>errors.push(String(error)));
      const url = new URL((language==='en'?'en/':'')+'request-lifecycle.html',base).href;
      await page.goto(url,{waitUntil:'networkidle'});
      await page.waitForFunction(()=>[...document.querySelectorAll('.mermaid')].every(e=>e.dataset.ready==='true'),undefined,{timeout:60000});
      assert.equal(await page.locator('.diagram-error').count(),0);
      const run = {language,mobile,url,figures:[],errors};
      run.layout = await page.evaluate(()=>({width:innerWidth,body:document.body.scrollWidth,document:document.documentElement.scrollWidth}));
      assert.ok(run.layout.body<=run.layout.width+1 && run.layout.document<=run.layout.width+1,'Page must not overflow horizontally');
      await page.screenshot({path:path.join(out,`${language}-${mobile?'mobile':'desktop'}-start.png`)});
      for (const id of ids) {
        const link = page.locator(`article a[href$=".${id}.mmd"]`).first();
        assert.equal(await link.count(),1,id);
        const href = await link.getAttribute('href');
        const original = await context.request.get(new URL(href,url).href);
        assert.ok(original.ok());
        assert.match(await original.text(),/flowchart/);
        const index = await link.evaluate(a=>{
          let node=a.closest('p').previousElementSibling;
          while(node && !node.classList.contains('mermaid'))node=node.previousElementSibling;
          if(!node)throw Error('No adjacent question diagram');
          return [...document.querySelectorAll('.mermaid')].indexOf(node);
        });
        const figure = page.locator('.mermaid').nth(index);
        await figure.scrollIntoViewIfNeeded();
        await figure.focus();
        await page.keyboard.press('Enter');
        await page.locator('#diagram-dialog').waitFor({state:'visible'});
        const label = await page.locator('#diagram-viewport .node').first().textContent();
        const query = label.trim().slice(0,2);
        assert.ok(query);
        await page.locator('#node-search').fill(query);
        assert.ok(await page.locator('#diagram-viewport .is-match').count());
        const before = await page.locator('#diagram-viewport svg').evaluate(e=>e.getBoundingClientRect().width);
        await page.locator('#zoom-in').click();
        const after = await page.locator('#diagram-viewport svg').evaluate(e=>e.getBoundingClientRect().width);
        assert.ok(after>before);
        const nodes = await page.locator('#diagram-viewport .node').count();
        assert.ok(nodes>=2 && nodes<=(id==='callback-order-flow'?11:9));
        await page.screenshot({path:path.join(out,`${language}-${mobile?'mobile':'desktop'}-${id}.png`)});
        await page.keyboard.press('Escape');
        await page.locator('#diagram-dialog').waitFor({state:'hidden'});
        assert.ok(await figure.evaluate(e=>e===document.activeElement));
        run.figures.push({id,index,nodes,source:href,query});
      }
      const local = page.locator('article a[href^="#source-"]');
      assert.ok(await local.count());
      const target = await local.first().getAttribute('href');
      while (!(await local.first().isVisible())) {
        const closed = page.locator('details:not([open])').filter({has:page.locator(`a[href="${target}"]`)}).first();
        assert.ok(await closed.count(),'Hidden evidence link needs an expandable ancestor');
        await closed.locator(':scope > summary').click();
      }
      await local.first().click();
      const destination = page.locator(target);
      await destination.waitFor({state:'visible'});
      run.evidence_anchor = target;
      const sourceLink = page.locator('article a[href*="/blob/be7e83e91348250c015aad6d6f59f1468555bae8/"]').first();
      assert.ok(await sourceLink.count());
      run.source_url = await sourceLink.getAttribute('href');
      const citations = await page.locator('details.source-excerpts a[href*="/blob/"]').evaluateAll(links=>links.map(a=>a.href));
      assert.ok(citations.length,'Source appendix must contain original code links');
      assert.ok(citations.every(href=>href.includes('/blob/be7e83e91348250c015aad6d6f59f1468555bae8/')),'Every current source appendix citation must use the frozen current commit');
      run.current_source_links = citations.length;
      await page.keyboard.press('Control+k');
      await page.locator('#search-dialog').waitFor({state:'visible'});
      await page.locator('#search-input').fill('UVC');
      await page.waitForFunction(()=>document.querySelector('#search-results a'));
      run.search_results = await page.locator('#search-results a').count();
      await page.keyboard.press('Escape');
      assert.equal(errors.length,0);
      report.runs.push(run);
      await context.close();
    }
    report.status='passed';
    await fs.writeFile(path.join(out,'summary.json'),JSON.stringify(report,null,2));
    console.log(JSON.stringify(report));
  } catch(error) {
    report.status='failed';report.error=String(error);
    await fs.writeFile(path.join(out,'failure.json'),JSON.stringify(report,null,2));
    throw error;
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
