"""Exercise navigation lifecycle logic without a browser or third-party JS packages.

Browser checks still cover native disclosure events, layout and keyboard focus.
"""
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_sidebar_fold_lifecycle():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed for the navigation lifecycle regression check')
    result = subprocess.run([node, '-e', r'''
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('src/sdd/site_assets/site.js', 'utf8');
const block = source.slice(source.indexOf('  // Keep navigation context'),
  source.indexOf("  document.querySelectorAll('dialog [data-close]')"));
class Events {
  constructor() { this.events = {}; }
  addEventListener(name, fn) { (this.events[name] ||= []).push(fn); }
  fire(name) { for (const fn of this.events[name] || []) fn({type: name}); }
}
const values = new Map();
let blocked = false;
const storage = {
  getItem(key) { if (blocked) throw Error('blocked'); return values.get(key) ?? null; },
  setItem(key, value) { if (blocked) throw Error('blocked'); values.set(key, value); }
};
function page({path='/site/', mobile=false, current=false}={}) {
  const order = [];
  const folds = ['group', 'task', 'branch'].map(id => {
    const fold = new Events();
    fold.dataset = {navId: id};
    fold.summary = new Events();
    fold.querySelector = () => fold.summary;
    let open = false;
    Object.defineProperty(fold, 'open', {get: () => open, set: value => {
      order.push(id); open = value;
    }});
    return fold;
  });
  const sidebar = new Events();
  const currentLink = current ? {parentElement:folds[2], closest:() => folds[2]} : null;
  sidebar.querySelector = selector => selector === 'a[aria-current="page"]' ? currentLink : null;
  sidebar.querySelectorAll = () => folds;
  let scroll = 0;
  Object.defineProperty(sidebar, 'scrollTop', {get: () => scroll, set: value => {
    order.push('scroll');
    scroll = Math.min(value, folds.every(fold => fold.open) ? 500 : 100);
  }});
  const win = new Events();
  const desktop = new Events(); desktop.matches = !mobile;
  vm.runInNewContext(block, {sidebar, window: win, desktop, sessionStorage: storage,
    storageRoot: {pathname: path}});
  return {folds, sidebar, win, order};
}
const key = 'sdd.sidebar.folds:/site/';
// Every menu starts closed. Initial events do not create user preferences.
let a = page(); a.folds[0].fire('toggle');
assert.deepEqual(a.folds.map(fold => fold.open), [false,false,false]);
assert.deepEqual(JSON.parse(values.get(key)).states, {});
let b = page({current:true}); assert.equal(b.folds[2].open, false);
// Two native activations may coalesce into one toggle at the starting value.
// Keep that explicit closed choice rather than dropping it as a default.
b.folds[2].summary.fire('click'); b.folds[2].open = true;
b.folds[2].summary.fire('click'); b.folds[2].open = false;
b.folds[2].fire('toggle');
assert.deepEqual(JSON.parse(values.get(key)).states, {branch:false});
// Full pagehide snapshot catches multiple fast changes before any toggle event.
b.folds[0].open = true; b.folds[1].open = true; b.folds[2].open = true;
b.win.fire('pagehide');
assert.deepEqual(JSON.parse(values.get(key)).states, {group:true, task:true, branch:true});
a = page();
assert.deepEqual(a.folds.map(fold => fold.open), [true,true,true]);
// Closing/reopening an ancestor never changes explicit nested open choices.
a.folds[0].open = false; a.win.fire('pagehide');
b = page();
assert.deepEqual(b.folds.map(fold => fold.open), [false,true,true]);
b.folds[0].open = true; b.folds[0].fire('toggle');
assert.deepEqual(b.folds.map(fold => fold.open), [true,true,true]);
// Closing a parent does not overwrite nested choices, including explicit false
// on the current branch. Navigation, reload and another edition share these IDs.
b.folds[2].open = false; b.folds[2].fire('toggle');
b.folds[0].open = false; b.win.fire('pagehide');
b = page({current:true});
assert.deepEqual(b.folds.map(fold => fold.open), [false,true,false]);
b.folds[0].open = true; b.folds[0].fire('toggle');
assert.deepEqual(b.folds.map(fold => fold.open), [true,true,false]);
// Restore the latest choices onto an older BFCache document, before restoring
// its scroll (the fake layout clamps at 100 unless every fold has opened).
values.set(key, JSON.stringify({version:1, states:{group:true,task:true,branch:true}}));
values.set('sdd.sidebar.scroll:/site/', '350');
a.order.length = 0; a.win.fire('pageshow');
assert.deepEqual(a.order, ['group','task','branch','scroll']);
assert.equal(a.sidebar.scrollTop, 350);
a.folds[0].fire('toggle');
assert.deepEqual(JSON.parse(values.get(key)).states, {group:true,task:true,branch:true});
// Different deployments on this origin do not share choices. Mobile restores
// folds without writing its panel offset into desktop scroll or scrolling body.
assert.deepEqual(page({path:'/other/'}).folds.map(fold => fold.open), [false,false,false]);
const mobile = page({mobile:true}); mobile.sidebar.scrollTop = 80;
mobile.folds[0].open = false; mobile.win.fire('pagehide');
assert.equal(values.get('sdd.sidebar.scroll:/site/'), '350');
assert.equal(mobile.order.filter(value => value === 'scroll').length, 1);
// Corruption, wrong versions, nonboolean entries and arrays are safe defaults.
for (const bad of ['{', 'null', '[]', '{"version":2,"states":{"group":false}}',
                   '{"version":1,"states":[]}', '{"version":1,"states":{"group":"false"}}']) {
  values.set(key, bad);
  const fresh = page();
  assert.deepEqual(fresh.folds.map(fold => fold.open), [false,false,false]);
}
blocked = true;
const noStorage = page(); noStorage.folds[0].open = true;
noStorage.folds[0].fire('toggle'); noStorage.win.fire('pagehide');
noStorage.win.fire('pageshow');
assert.equal(noStorage.folds[0].open, true);
// Closed details may contain a geometrically measurable descendant in some
// engines. Focus selection and the tab trap must use disclosure ancestry too.
const reader = fs.readFileSync('src/sdd/site_assets/reader-tools.js', 'utf8');
const focusBlock = reader.slice(reader.indexOf('  function visibleMenuTarget'), reader.indexOf('  function setMenu'));
const sidebar = {};
const chooseTarget = vm.runInNewContext(`(${focusBlock.trim()})`, {sidebar});
function detail(parent, open) {
  const node = {parentElement:parent, open, matches() { return !this.open; }};
  node.summary = {parentElement:node}; node.querySelector = () => node.summary;
  return node;
}
const outer = detail(sidebar, false), inner = detail(outer, false);
const link = {parentElement:inner};
assert.equal(chooseTarget(link), outer.summary);
assert.equal(chooseTarget(inner.summary), outer.summary);
assert.equal(chooseTarget(outer.summary), outer.summary);
outer.open = true; assert.equal(chooseTarget(link), inner.summary);
inner.open = true; assert.equal(chooseTarget(link), link);
console.log('navigation lifecycle checks passed');
'''], cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
