const {chromium} = require('playwright');
const fs = require('node:fs/promises');
const path = require('node:path');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const base = process.argv[2];
const out = path.resolve(process.argv[3]);
if (!/^https?:\/\//.test(base)) throw Error('Supply the exact local or public base URL');
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
async function snapshot(page) {
  return page.locator('#diagram-viewport').evaluate(v => {
    const svg=v.querySelector('svg'),rect=v.getBoundingClientRect();
    return {left:v.scrollLeft,top:v.scrollTop,width:v.clientWidth,height:v.clientHeight,
      scrollWidth:v.scrollWidth,scrollHeight:v.scrollHeight,rect:rect.toJSON(),
      scale:document.querySelector('#zoom-value').textContent,
      panning:v.classList.contains('is-panning'),canPan:v.classList.contains('can-pan'),
      touchAction:getComputedStyle(v).touchAction,cursor:getComputedStyle(v).cursor,
      pageX:scrollX,pageY:scrollY,svgWidth:svg.getBoundingClientRect().width,
      nodes:svg.querySelectorAll('.node').length,edges:svg.querySelectorAll('.flowchart-link').length,
      matches:svg.querySelectorAll('.is-match').length};
  });
}
async function touchDrag(page,cdp,from,to,cancel=false) {
  await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:from.x,y:from.y,id:1}]});
  for(let i=1;i<=12;i++) {
    await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{id:1,x:from.x+(to.x-from.x)*i/12,y:from.y+(to.y-from.y)*i/12}]});
    await page.waitForTimeout(16);
  }
  // Let velocity settle before release, so assertions measure the same pan
  // rather than depending on the browser's subsequent fling distance.
  await page.waitForTimeout(120);
  await cdp.send('Input.dispatchTouchEvent',{type:cancel?'touchCancel':'touchEnd',touchPoints:[]});
}
(async()=>{
  await fs.mkdir(out,{recursive:false});
  const browser = await chromium.launch({channel:'chrome',headless:true});
  const report={schema:1,base,startedAt:new Date().toISOString(),engine:browser.version(),
    playwright:require('playwright/package.json').version,
    isolation:'Fresh nonpersistent contexts; no user Chrome profile or Windows UI access',
    scope:'Chromium mouse and mobile touch emulation, not a physical phone or camera test',runs:[]};
  try {
    for(const mobile of [false,true]) for(const lang of ['ko','en']) {
      const context=await browser.newContext({viewport:mobile?{width:390,height:844}:{width:1280,height:900},
        hasTouch:mobile,isMobile:mobile,deviceScaleFactor:1});
      await context.addInitScript(()=>{
        window.__panEvidence=[];
        for(const type of ['pointerdown','pointermove','pointerup','pointercancel','touchstart','touchmove','touchend','touchcancel'])
          addEventListener(type,event=>{
            if(!event.target.closest?.('#diagram-viewport'))return;
            const v=document.querySelector('#diagram-viewport');
            const row={type,pointerType:event.pointerType||null,isTrusted:event.isTrusted,
              x:event.clientX??event.touches?.[0]?.clientX??null,y:event.clientY??event.touches?.[0]?.clientY??null,
              time:event.timeStamp,panning:v.classList.contains('is-panning')};
            window.__panEvidence.push(row);
            queueMicrotask(()=>{row.defaultPrevented=event.defaultPrevented;});
          },{capture:true,passive:true});
      });
      const page=await context.newPage(),messages=[],exceptions=[];
      page.on('console',msg=>{if(['error','warning'].includes(msg.type()))messages.push({type:msg.type(),text:msg.text(),location:msg.location()});});
      page.on('pageerror',e=>exceptions.push(String(e)));
      const url=new URL((lang==='en'?'en/':'')+'official-cam-validation.html',base).href;
      await page.goto(url,{waitUntil:'networkidle'});
      await page.locator('.mermaid[data-ready=true]').last().waitFor();
      assert.equal(await page.locator('.mermaid[data-ready=true]').count(),6);
      const names=lang==='ko'?{open:'다이어그램 확대',search:'요소 찾기',fit:'화면에 맞춤',plus:'확대',close:'닫기 Esc'}:
        {open:'Enlarge diagram',search:'Find elements',fit:'Fit to screen',plus:'Zoom in',close:'Close Esc'};
      const queries=lang==='ko'?['매핑','보류','버퍼','카메라','이벤트','승인']:['Virtual2','RequestPending','camera start','Async','captureDone','Kconfig'];
      const run={lang,mobile,url,device:await page.evaluate(()=>({width:innerWidth,height:innerHeight,maxTouchPoints:navigator.maxTouchPoints,coarse:matchMedia('(pointer:coarse)').matches})),figures:[]};
      const cdp=mobile?await context.newCDPSession(page):null;
      if(mobile)assert.ok(run.device.maxTouchPoints>0&&run.device.coarse);
      for(let i=0;i<6;i++) {
        const trigger=page.getByRole('button',{name:names.open,exact:true}).nth(i);
        if(mobile)await trigger.tap();else await trigger.click();
        const opened=await snapshot(page);
        assert.equal(opened.scale,'114%');
        assert.equal(opened.nodes,[9,9,7,9,10,12][i]);
        assert.equal(opened.edges,[9,10,9,10,9,14][i]);
        // Guarantee enough overflow to verify both axes, including desktop.
        for(let n=0;n<9;n++){
          const s=await snapshot(page);
          if(s.scrollWidth-s.width>180&&s.scrollHeight-s.height>180)break;
          if(mobile)await page.getByRole('button',{name:names.plus,exact:true}).tap();
          else await page.getByRole('button',{name:names.plus,exact:true}).click();
        }
        const before=await snapshot(page);
        const from={x:before.rect.x+before.width*.7,y:before.rect.y+before.height*.65};
        const to={x:from.x-(mobile?90:150),y:from.y-(mobile?100:110)};
        const evidenceStart=await page.evaluate(()=>window.__panEvidence.length);
        if(mobile)await touchDrag(page,cdp,from,to);
        else{await page.mouse.move(from.x,from.y);await page.mouse.down();await page.mouse.move(to.x,to.y,{steps:12});await page.mouse.up();}
        await page.waitForFunction(()=>!document.querySelector('#diagram-viewport').classList.contains('is-panning'));
        const moved=await snapshot(page);
        const events=await page.evaluate(n=>window.__panEvidence.slice(n),evidenceStart);
        assert.ok(moved.left>before.left+25&&moved.top>before.top+25,'Both axes must move');
        assert.equal(moved.scale,before.scale);assert.equal(moved.pageY,before.pageY);assert.equal(moved.pageX,before.pageX);
        assert.ok(events.length&&events.every(e=>e.isTrusted),'Use real browser input, not DOM-dispatched events');
        if(mobile){assert.ok(events.some(e=>e.pointerType==='touch'));assert.ok(events.some(e=>e.type==='touchmove'));assert.ok(events.every(e=>!e.panning&&!e.defaultPrevented));}
        else{assert.ok(events.some(e=>e.pointerType==='mouse'));assert.ok(events.some(e=>e.type==='pointermove'&&e.panning));}
        const figure={i,opened,before,moved,events};
        if(i===0)await page.screenshot({path:path.join(out,`${lang}-${mobile?'touch':'mouse'}-moved.png`)});
        if(i===4){
          if(mobile){await touchDrag(page,cdp,from,to,true);figure.cancelled=await snapshot(page);}
          else{await page.mouse.move(from.x,from.y);await page.mouse.down();await page.mouse.move(from.x,before.rect.y-10,{steps:10});await page.mouse.up();figure.outsideRelease=await snapshot(page);}
          assert.equal((await snapshot(page)).panning,false);
        }
        await page.getByRole('searchbox',{name:names.search,exact:true}).fill(queries[i]);
        figure.searched=await snapshot(page);assert.ok(figure.searched.matches>0);assert.equal(figure.searched.scale,moved.scale);
        if(mobile)await page.getByRole('button',{name:names.fit,exact:true}).tap();else await page.getByRole('button',{name:names.fit,exact:true}).click();
        figure.fit=await snapshot(page);assert.equal(figure.fit.panning,false);assert.equal(figure.fit.canPan,false);
        await page.keyboard.press('Escape');await page.locator('#diagram-dialog').waitFor({state:'hidden'});
        await page.waitForFunction(()=>document.querySelectorAll('article .mermaid svg').length===6);
        assert.equal(await page.locator('article .mermaid svg').count(),6);
        assert.equal(await page.evaluate(()=>document.activeElement.getAttribute('aria-label')),names.open);
        run.figures.push(figure);
      }
      run.console=messages;run.exceptions=exceptions;
      await fs.writeFile(path.join(out,`${lang}-${mobile?'touch':'mouse'}.json`),JSON.stringify(run,null,2));
      assert.equal(exceptions.length,0);
      assert.ok(messages.every(m=>new URL(m.location.url||url).pathname==='/favicon.ico'&&m.text.includes('404')),'Unexpected browser console warning/error');
      const script=await page.locator('script[src*="assets/site.js"]').getAttribute('src');
      const asset=await context.request.get(new URL(script,url).href);assert.ok(asset.ok());
      run.script={url:new URL(script,url).href,sha256:hash(await asset.body())};
      await fs.writeFile(path.join(out,`${lang}-${mobile?'touch':'mouse'}.json`),JSON.stringify(run,null,2));
      report.runs.push({lang,mobile,figures:run.figures.length,script:run.script,exceptions:exceptions.length});
      await context.close();
    }
    report.status='passed';report.completedAt=new Date().toISOString();
    await fs.writeFile(path.join(out,'summary.json'),JSON.stringify(report,null,2));
    console.log(JSON.stringify(report));
  }catch(error){report.status='failed';report.error=String(error);await fs.writeFile(path.join(out,'failure.json'),JSON.stringify(report,null,2));throw error;}
  finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
