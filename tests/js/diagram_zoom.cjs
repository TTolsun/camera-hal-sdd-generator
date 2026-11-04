const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('src/sdd/site_assets/site.js', 'utf8');
const block = source.slice(source.indexOf('  const diagramDialog'), source.indexOf('  const diagrams ='));
class Element {
  constructor() { this.events = {}; this.style = {}; this.textContent = ''; }
  addEventListener(name, fn) { this.events[name] = fn; }
  fire(name) { this.events[name]?.(); }
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
console.log('readable opening, bounds, transformations, resize modes and restore passed');
