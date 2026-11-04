const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('src/sdd/site_assets/site.js', 'utf8');
const block = source.slice(source.indexOf('  const diagramDialog'), source.indexOf('  const diagrams ='));
class Element {
  constructor() { this.events = {}; this.style = {}; this.textContent = ''; const names=new Set(); this.classList={add:n=>names.add(n),remove:n=>names.delete(n),contains:n=>names.has(n),toggle(n,on){if(on)names.add(n);else names.delete(n);}}; }
  addEventListener(name, fn) { this.events[name] = fn; }
  fire(name, event={}) { this.events[name]?.(event); }
  focus() { this.focused = true; }
}
const elements = Object.fromEntries(['diagram-dialog','diagram-viewport','diagram-canvas','node-search',
  'zoom-value','node-count','diagram-title','zoom-in','zoom-out','zoom-reset','zoom-fit'].map(id => ['#'+id,new Element()]));
const viewport = elements['#diagram-viewport'];
Object.assign(viewport,{clientWidth:400,clientHeight:300,scrollLeft:0,scrollTop:0,
  scrollTo(x,y){ this.scrollLeft=x; this.scrollTop=y; }});
const win = new Element();
let bodyFont = 16, labels = [], restored = false, oldStyle = null;
const svg = {style:{},viewBox:{baseVal:{width:2000,height:1000}},
  width:{baseVal:{unitType:1,value:2000}},height:{baseVal:{unitType:1,value:1000}},
  getAttribute(){return oldStyle;},setAttribute(k,v){this.restoredStyle=v;},removeAttribute(){this.restoredStyle=null;},
  before(){},querySelectorAll(selector){return selector.includes('foreignObject')?labels.filter(e=>e.html||selector.split(', ').includes(e.tagName)):[];},
  getBoundingClientRect(){return {width:parseFloat(this.style.width),height:parseFloat(this.style.height)};}};
Object.defineProperties(viewport,{scrollWidth:{get:()=>Math.max(viewport.clientWidth,parseFloat(svg.style.width)+56)},scrollHeight:{get:()=>Math.max(viewport.clientHeight,parseFloat(svg.style.height)+56)}});
let captured=null;
viewport.setPointerCapture=id=>{captured=id;};
viewport.hasPointerCapture=id=>captured===id;
viewport.releasePointerCapture=()=>{captured=null;};
viewport.getBoundingClientRect=()=>({left:10,top:20});
viewport.clientLeft=viewport.clientTop=1;
const trigger = {querySelector(){return svg;}, getAttribute(){return 'Flow';}, focus(){this.focused=true;}};
elements['#diagram-canvas'].append=()=>{};
elements['#diagram-dialog'].showModal=()=>{};
const body = {};
class Matrix {
  constructor(value) { const v=Array.isArray(value)?value:value?.match?.(/matrix\(([^)]+)\)/)?.[1].split(',').map(Number); [this.a,this.b,this.c,this.d]=v||[1,0,0,1]; this.e=this.f=0; }
  multiply(m) { const n=new Matrix(); Object.assign(n,{a:this.a*m.a+this.c*m.b,b:this.b*m.a+this.d*m.b,c:this.a*m.c+this.c*m.d,d:this.b*m.c+this.d*m.d});return n; }
  scale(s) { const n=new Matrix(); n.a=n.d=s; return this.multiply(n); }
}
const context = {document:{body,querySelector:id=>elements[id],createComment:()=>({replaceWith(){restored=true;}})},
  window:win,DOMMatrix:Matrix,getComputedStyle:e=>e===body?{fontSize:`${bodyFont}px`}:e.computed,t:(_,en)=>en};
vm.createContext(context); vm.runInContext(block,context);
function label(font,unit=1,html=false,hidden=false){
  const owner={getScreenCTM:()=>new Matrix().scale(unit)};
  return {tagName:html?'span':'text',html,parentElement:owner,computed:{fontSize:`${font}px`,visibility:hidden?'hidden':'visible',display:'block',transform:'none',zoom:'1'},
    childNodes:[{nodeType:3,textContent:'label'}],
    getBoundingClientRect:()=>({width:80,height:20}),closest:()=>owner,
    ...(html?{}:{getScreenCTM:owner.getScreenCTM})};
}
function open(){vm.runInContext('openDiagram(trigger)',Object.assign(context,{trigger}));}
function value(){return parseFloat(svg.style.width)/2000;}
function near(a,b){assert.ok(Math.abs(a-b)<1e-8,`${a} != ${b}`);}
// Small edge text dictates reading scale, including a transformed HTML label.
labels=[label(14),label(10,.5,true),label(1,1,false,true)]; open(); near(value(),3.2);
viewport.scrollLeft=500; win.fire('resize'); near(value(),3.2); assert.equal(viewport.scrollLeft,500);
elements['#zoom-in'].fire('click'); near(value(),4); win.fire('resize'); near(value(),4);
elements['#zoom-out'].fire('click'); near(value(),3.2);
elements['#zoom-reset'].fire('click'); near(value(),1); win.fire('resize'); near(value(),1);
elements['#zoom-fit'].fire('click'); near(value(),.17);
viewport.clientWidth=600; win.fire('resize'); near(value(),.24);
elements['#diagram-dialog'].fire('close'); assert.ok(restored && trigger.focused);
// Reopening remeasures; it does not inherit the previous Fit mode.
oldStyle='color:red'; labels=[label(24)]; open(); near(value(),1);
elements['#diagram-dialog'].fire('close'); assert.equal(svg.restoredStyle,oldStyle);
// Inaccessible/empty measurements do not collapse to 5% or create NaN.
labels=[];open();near(value(),1);
labels=[label(NaN),label(0)];open();near(value(),1);
labels=[label(1)];open();near(value(),8);
bodyFont=20;labels=[label(10)];open();near(value(),2);
bodyFont=16;
const html=label(16,1,true); html.computed.transform='matrix(0.5,0,0,0.5,0,0)';
// Legacy SVGMatrix must not receive DOMMatrix in multiply(), as in WebKit.
html.parentElement.getScreenCTM=()=>({a:1,b:0,c:0,d:1,e:0,f:0,multiply(){throw Error('incompatible SVGMatrix argument');}});
labels=[html];open();near(value(),2);
html.parentElement={parentElement:html.parentElement,computed:{transform:'matrix(0,-1,1,0,0,0)',zoom:'0.5'}};
open();near(value(),4);
// Fit must remain a full overview even when its scale is below manual limits.
svg.viewBox.baseVal.width=20000;open();elements['#zoom-fit'].fire('click');
near(parseFloat(svg.style.width)/20000,.027);
const curved=label(8);curved.tagName='textPath';labels=[curved];open();
near(parseFloat(svg.style.width)/20000,2);
// With no viewBox, use explicit SVG dimensions before inline CSS fit size.
svg.viewBox.baseVal={width:0,height:0};svg.width.baseVal.value=200;svg.height.baseVal.value=100;
labels=[];open();assert.equal(svg.style.width,'200px');assert.equal(svg.style.height,'100px');
// Mouse drag moves the actual scroll position without changing zoom. Native
// touch, scrollbars, links and modified/non-primary clicks remain untouched.
svg.viewBox.baseVal={width:2000,height:1000};viewport.clientWidth=400;viewport.clientHeight=300;open();
function pointer(changes={}) {return {pointerType:'mouse',pointerId:7,button:0,buttons:1,clientX:210,clientY:180,
  target:{closest:()=>null},preventDefault(){this.prevented=true;},...changes};}
viewport.scrollLeft=300;viewport.scrollTop=400;
const down=pointer();viewport.fire('pointerdown',down);
assert.ok(down.prevented && captured===7 && viewport.classList.contains('is-panning'));
viewport.fire('pointermove',pointer({clientX:140,clientY:100}));
assert.equal(viewport.scrollLeft,370);assert.equal(viewport.scrollTop,480);near(value(),1);
viewport.fire('pointermove',pointer({pointerId:8,clientX:90}));assert.equal(viewport.scrollLeft,370);
viewport.fire('pointerup',pointer());assert.equal(captured,null);assert.ok(!viewport.classList.contains('is-panning'));
for(const kind of [{pointerType:'touch'},{pointerType:'pen'},{button:2},{ctrlKey:true},{altKey:true},{metaKey:true},
  {target:{closest:()=>({})}},{clientX:411},{clientY:321}]){
  const event=pointer(kind);viewport.fire('pointerdown',event);assert.ok(!event.prevented && captured===null);
}
for(const event of ['pointercancel','lostpointercapture']){
  viewport.fire('pointerdown',pointer());viewport.fire(event,pointer());assert.equal(captured,null);
}
for(const event of ['blur','resize']){
  viewport.fire('pointerdown',pointer());win.fire(event);assert.equal(captured,null);
}
viewport.fire('pointerdown',pointer());viewport.fire('pointermove',pointer({buttons:0}));assert.equal(captured,null);
viewport.fire('pointerdown',pointer());elements['#zoom-in'].fire('click');assert.equal(captured,null);
viewport.fire('pointerdown',pointer());elements['#diagram-dialog'].fire('close');assert.equal(captured,null);
open();elements['#zoom-fit'].fire('click');assert.ok(!viewport.classList.contains('can-pan'));
const fitDown=pointer();viewport.fire('pointerdown',fitDown);assert.ok(!fitDown.prevented);
console.log('readable opening, bounds, transformations, resize modes and restore passed');
