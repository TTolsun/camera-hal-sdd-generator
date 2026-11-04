const {chromium}=require('playwright');
const fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const base=process.argv[2],out=path.resolve(process.argv[3]);
const expectedRoot=path.resolve(process.argv[4]);
if(!/^http:\/\/127\.0\.0\.1:\d+\/$/.test(base))throw Error('Use a specific local public-artifact preview URL');
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const targets=[
 {page:'vendor-overview',id:'hardware-boundary',nodes:4,search:'Camera'},
 {page:'request-lifecycle',id:'stop-device-observation-plan',nodes:7,search:'stopDevice'},
 {page:'request-lifecycle',id:'request-completion-audit-plan',nodes:5,search:'completeRequest'}
];
(async()=>{
 await fs.mkdir(out,{recursive:false});
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const report={started_at:new Date().toISOString(),base,chrome:browser.version(),playwright:require('playwright/package.json').version,
  assessment:'Automated fresh-context browser interaction; no human reader or physical device evaluation',runs:[],status:'running'};
 try{
  report.preflight=[];
  const request=await browser.newContext();
  for(const file of ['assets/site.js','assets/reading.css',...['','en/'].flatMap(prefix=>['vendor-overview','request-lifecycle','request-diagnosis'].map(name=>prefix+name+'.html'))]){
   const response=await request.request.get(new URL(file,base).href);assert.equal(response.status(),200);
   const actual=sha(await response.body()),expected=sha(await fs.readFile(path.join(expectedRoot,file)));
   report.preflight.push({file,actual,expected});assert.equal(actual,expected,'Preview server response differs from the exact intended artifact: '+file);
  }
  await request.close();
  for(const mobile of [false,true])for(const lang of ['ko','en']){
   const ctx=await browser.newContext({viewport:mobile?{width:390,height:844}:{width:1280,height:900},isMobile:mobile,hasTouch:mobile,deviceScaleFactor:1});
   const page=await ctx.newPage(),errors=[];page.on('pageerror',e=>errors.push(String(e)));
   const prefix=lang==='en'?'en/':'',run={lang,mobile,figures:[],links:[],pages:{}};report.runs.push(run);
   for(const spec of targets){
    const url=new URL(prefix+spec.page+'.html',base).href;
    if(page.url()!==url){
     const response=await page.goto(url,{waitUntil:'networkidle'});assert.equal(response.status(),200);
     run.pages[spec.page]=sha(await response.body());
     assert.equal(run.pages[spec.page],sha(await fs.readFile(path.join(expectedRoot,prefix+spec.page+'.html'))));
     await page.waitForFunction(()=>[...document.querySelectorAll('.mermaid')].every(n=>n.dataset.ready==='true'),{},{timeout:90000});
     assert.equal(await page.locator('.diagram-error').count(),0);
     const widths=await page.evaluate(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth}));
     assert.ok(widths.document<=widths.viewport+1,JSON.stringify(widths));
    }
    const trigger=page.locator('a[href="'+spec.page+'.'+spec.id+'.mmd"]').locator('xpath=preceding::*[contains(concat(" ",normalize-space(@class)," ")," mermaid ")][1]');
    assert.equal(await trigger.count(),1);await trigger.scrollIntoViewIfNeeded();
    run.current_figure={spec,trigger:await trigger.evaluate(e=>({id:e.id,title:e.dataset.title,nodes:e.querySelectorAll('svg .node').length}))};
    const originalId=await trigger.getAttribute('id');
    if(mobile)await trigger.tap();else await trigger.click();
    await page.locator('#diagram-dialog[open]').waitFor();
    const viewport=page.locator('#diagram-viewport');
    run.current_figure.opened=await page.locator('#diagram-dialog').evaluate(e=>({title:e.querySelector('#diagram-title').textContent,nodes:[...e.querySelectorAll('svg .node')].map(n=>n.textContent)}));
    assert.equal(await viewport.locator('svg .node').count(),spec.nodes);
    const search=page.locator('#node-search');await search.fill(spec.search);
    await page.waitForFunction(()=>document.querySelectorAll('#diagram-viewport .is-match').length>0);
    const matches=await viewport.locator('.is-match').count();
    await search.fill('');assert.equal(await viewport.locator('.is-match').count(),0);
    await page.locator('#zoom-fit').click();
    const fit=await page.locator('#zoom-value').textContent();assert.ok(parseInt(fit)>0);
    await page.locator('#zoom-in').click();
    const zoom=await page.locator('#zoom-value').textContent();assert.ok(parseInt(zoom)>parseInt(fit));
    await page.locator('#zoom-fit').click();
    const image=lang+'-'+(mobile?'mobile':'desktop')+'-'+spec.id+'.png';
    await page.screenshot({path:path.join(out,image)});
    await page.keyboard.press('Escape');assert.equal(await page.locator('#diagram-dialog[open]').count(),0);
    assert.ok(await trigger.evaluate(e=>document.activeElement===e));
    run.figures.push({id:spec.id,nodes:spec.nodes,search:spec.search,matches,fit,zoom,image,originalId});
   }
   const url=new URL(prefix+'request-diagnosis.html',base).href;
   const response=await page.goto(url,{waitUntil:'networkidle'});assert.equal(response.status(),200);run.pages['request-diagnosis']=sha(await response.body());
   const links=await page.locator('p.reading-links a').evaluateAll(es=>es.map(e=>({href:e.href,text:e.textContent})));
   assert.equal(links.length,3,'Exactly three new topic links');
   for(const link of links){
    assert.ok(link.href.startsWith(base+prefix));assert.ok(new URL(link.href).hash);
    await page.locator('p.reading-links a').filter({hasText:link.text}).click();
    await page.waitForURL(link.href);const id=decodeURIComponent(new URL(page.url()).hash.slice(1));
    await page.waitForFunction(()=>[...document.querySelectorAll('.mermaid')].every(n=>n.dataset.ready==='true'),{},{timeout:90000});
    await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
    const target=await page.evaluate(id=>{const e=document.getElementById(id);if(!e)return null;const r=e.getBoundingClientRect();return {tag:e.tagName,text:e.textContent,top:r.top,height:r.height};},id);
    assert.ok(target&&target.tag==='H2',JSON.stringify(target));
    assert.ok(target.top>=-1&&target.top< (mobile?844:900),JSON.stringify(target));
    run.links.push({...link,target});await page.goto(url,{waitUntil:'networkidle'});
   }
   assert.deepEqual(errors,[]);run.page_errors=errors;await ctx.close();
  }
  report.status='passed';
 }catch(e){report.status='failed';report.error=String(e);throw e;}
 finally{report.ended_at=new Date().toISOString();await fs.writeFile(path.join(out,'report.json'),JSON.stringify(report,null,2));await browser.close();}
})().catch(e=>{console.error(String(e));process.exitCode=1;});
