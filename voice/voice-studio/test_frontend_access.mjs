#!/usr/bin/env node
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const source = readFileSync(new URL('./web/app.js', import.meta.url), 'utf8');
const html = readFileSync(new URL('./web/index.html', import.meta.url), 'utf8');
const app = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
// These synthetically structured tokens are not credentials for any service.
const token = 'VSP-0123456789abcdef-abcdefghijklmnopqrstuvwx';
const site = 'https://studio.test/voice-studio/';
let sequence = 0;

class Element {
  constructor(tag, doc) {
    Object.assign(this, {tagName:tag, doc, children:[], listeners:{}, dataset:{}, attributes:{}, style:{}, hidden:false, disabled:false, open:false, value:'', src:'', textContent:'', className:'', isConnected:true});
    const classes = new Set();
    this.classList = {add:(...names)=>names.forEach(name=>classes.add(name)), remove:(...names)=>names.forEach(name=>classes.delete(name)), toggle:(name,on)=>on?classes.add(name):classes.delete(name)};
  }
  append(...elements) { this.children.push(...elements); }
  replaceChildren(...elements) { this.children = [...elements]; }
  setAttribute(name, value) { this.attributes[name] = value; }
  removeAttribute(name) { delete this.attributes[name]; if (name === 'src') this.src = ''; }
  addEventListener(name, listener) { (this.listeners[name] ??= []).push(listener); }
  async emit(name, event = {}) { event.preventDefault ??= () => {}; for (const listener of this.listeners[name] ?? []) await listener(event); }
  pause() {}
  load() {}
  focus() { if (!this.disabled) this.doc.activeElement = this; }
  select() {}
  close() { this.open = false; }
  querySelectorAll(selector) { return this.doc.select(this.children, selector); }
}

function createDocument() {
  const doc = {elements:[], activeElement:null};
  doc.select = (roots, selector) => {
    const all = []; const visit = node => { all.push(node); node.children.forEach(visit); }; roots.forEach(visit);
    return all.filter(element => selector === '[id]' ? Boolean(element.id) : selector === 'audio' ? element.tagName === 'audio' : selector === '[data-profile-action]' ? Boolean(element.dataset.profileAction) : selector.startsWith('.') ? element.className.split(' ').includes(selector.slice(1)) : false);
  };
  doc.querySelectorAll = selector => doc.select(doc.elements, selector);
  doc.createElement = tag => new Element(tag, doc);
  for (const match of html.matchAll(/<([\w-]+)\b([^>]*\bid="([^"]+)"[^>]*)>/g)) {
    const element = new Element(match[1], doc);
    Object.assign(element, {id:match[3], hidden:/\bhidden(?:\s|$)/.test(match[2]), disabled:/\bdisabled(?:\s|$)/.test(match[2]), className:/\bclass="([^"]*)"/.exec(match[2])?.[1] ?? ''});
    doc.elements.push(element);
  }
  return doc;
}

async function mount({isAdmin=false, hash='', loginStatus=200, profileStatus=200, qrAvailable=true} = {}) {
  const doc = createDocument(); const find = id => doc.elements.find(element => element.id === id);
  const old = Object.fromEntries(['document','window','fetch','navigator','VoiceStudioQr'].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  const calls = []; const events = []; const copies = []; const listeners = {};
  const location = {href:site + hash, hash};
  const history = {state:null, replaceState(state, title, url) { events.push('strip-fragment'); location.href = new URL(url, location.href).href; location.hash = new URL(location.href).hash; }};
  globalThis.document = doc;
  globalThis.window = {location, history, addEventListener(name, listener) { listeners[name] = listener; }};
  Object.defineProperty(globalThis, 'navigator', {configurable:true, value:{clipboard:{async writeText(value) { copies.push(value); }}}});
  globalThis.VoiceStudioQr = qrAvailable ? {toSvgDataUrl(value) { return 'data:image/svg+xml,' + encodeURIComponent(`<svg data-payload="${value}"></svg>`); }} : undefined;
  let authenticated = !hash;
  globalThis.fetch = async (url, options = {}) => {
    events.push('fetch'); calls.push({url, options, hash:location.hash});
    let status = 200; let body;
    if (url.endsWith('/api/login')) { status = loginStatus; authenticated = status === 200; body = authenticated ? {csrf:'test-csrf'} : {error:'Der Zugangscode ist nicht korrekt.'}; }
    else if (url.endsWith('/api/session')) body = {authenticated, is_admin:isAdmin, label:'Testperson', csrf:'test-csrf', recording_allowed:true, reference_text:'Ein deutscher Testtext.', max_recording_seconds:25};
    else if (url.endsWith('/api/profiles')) { status = profileStatus; body = status < 400 ? {profiles:[], selected_profile_id:null} : {error:'Die Stimmprofile sind vorübergehend nicht erreichbar.'}; }
    else if (url.endsWith('/api/access-codes') && options.method === 'POST') { status = 201; body = {access_code:{id:'personal-0123456789abcdef', label:'Neue Testperson', created_at_utc:'2026-10-13T10:00:00Z'}, code:token}; }
    else if (url.endsWith('/api/access-codes')) body = {access_codes:[{id:'personal-existing', label:'Bestehende Testperson', created_at_utc:'2026-10-13T09:00:00Z'}]};
    else if (url.endsWith('/api/logout')) body = {};
    else throw new Error('Unexpected endpoint');
    return {ok:status < 400, status, json:async()=>body};
  };
  const loaded = source.replaceAll('import.meta.url', JSON.stringify(site + 'app.js')) + `\n// isolated access test ${sequence++}`;
  await import('data:text/javascript;base64,' + Buffer.from(loaded).toString('base64'));
  await new Promise(setImmediate);
  return {doc, find, calls, events, copies, location, listeners, cleanup() { for (const [key, descriptor] of Object.entries(old)) { if (descriptor) Object.defineProperty(globalThis,key,descriptor); else delete globalThis[key]; } }};
}

test('personal login links put the personal token only in the fragment and reject administrator codes', () => {
  assert.equal(typeof app.personalLoginUrl, 'function');
  const url = new URL(app.personalLoginUrl(site + '?source=demo#old', token));
  assert.equal(url.origin + url.pathname, site);
  assert.equal(url.search, '');
  assert.equal(url.hash, '#access=' + token);
  assert.throws(() => app.personalLoginUrl(site, 'synthetic-administrator-code'), /persönlichen/);
});

test('QR opening strips the fragment before any API request and uses the existing login POST', async () => {
  const ui = await mount({hash:'#access=' + token});
  try {
    assert.equal(ui.events[0], 'strip-fragment');
    assert.equal(ui.location.hash, '');
    assert.ok(ui.calls.length >= 3);
    assert.ok(ui.calls.every(call => call.hash === '' && !call.url.includes(token)));
    assert.ok(ui.calls[0].url.endsWith('/api/login'));
    assert.equal(ui.calls[0].options.method, 'POST');
    assert.deepEqual(JSON.parse(ui.calls[0].options.body), {password:token});
    assert.equal(ui.calls[0].options.credentials, 'same-origin');
    assert.equal(ui.find('access-code').value, '');
    assert.equal(ui.find('studio-view').hidden, false);
    assert.equal(ui.find('session-label').textContent, 'Testperson');
    assert.equal(ui.find('admin-panel').hidden, true);
  } finally { ui.cleanup(); }
});

test('a failed QR login clears its token and leaves ordinary login available', async () => {
  const ui = await mount({hash:'#access=' + token, loginStatus:401});
  try {
    assert.equal(ui.location.hash, '');
    assert.equal(ui.find('access-code').value, '');
    assert.equal(ui.find('login-view').hidden, false);
    assert.equal(ui.find('login-button').disabled, false);
    assert.match(ui.find('page-message').textContent, /nicht korrekt/);
    assert.equal(ui.calls.filter(call => call.url.endsWith('/api/login')).length, 1);
    await ui.listeners.pageshow({persisted:true}); await new Promise(setImmediate);
    assert.equal(ui.calls.filter(call => call.url.endsWith('/api/login')).length, 1, 'back-forward cache must not replay the bearer token');
  } finally { ui.cleanup(); }
});

test('a profile-list failure after QR authentication preserves the confirmed personal session', async () => {
  const ui = await mount({hash:'#access=' + token, profileStatus:503});
  try {
    assert.equal(ui.find('studio-view').hidden, false);
    assert.equal(ui.find('login-view').hidden, true);
    assert.equal(ui.find('session-label').textContent, 'Testperson');
    assert.equal(ui.find('logout-button').hidden, false);
    assert.match(ui.find('page-message').textContent, /vorübergehend nicht erreichbar/);
    assert.equal(ui.location.hash, '');
    assert.equal(ui.find('access-code').value, '');
  } finally { ui.cleanup(); }
});

test('malformed or administrator fragments are stripped without an automatic login request', async () => {
  for (const hash of ['#access=synthetic-administrator-code', '#access=%E0%A4%A', '#access=' + token + '&access=' + token]) {
    const ui = await mount({hash});
    try { assert.equal(ui.location.hash, ''); assert.equal(ui.calls.some(call => call.url.endsWith('/api/login')), false); }
    finally { ui.cleanup(); }
  }
});

test('normal anchor navigation is preserved without QR login', async () => {
  const ui = await mount({hash:'#main-content'});
  try { assert.equal(ui.location.hash, '#main-content'); assert.equal(ui.calls.some(call => call.url.endsWith('/api/login')), false); }
  finally { ui.cleanup(); }
});

test('the administrator form is prominent and lists names without recovering secrets', async () => {
  const ui = await mount({isAdmin:true});
  try {
    assert.equal(ui.find('admin-panel').tagName, 'section');
    assert.equal(ui.find('admin-panel').hidden, false);
    assert.ok(html.indexOf('id="admin-panel"') < html.indexOf('class="active-card"'));
    assert.equal(ui.find('personal-access-list').children.length, 1);
    assert.match(ui.find('personal-access-list').children[0].textContent, /Bestehende Testperson/);
    assert.ok(ui.calls.some(call => call.url.endsWith('/api/access-codes') && !call.options.method));
    assert.doesNotMatch(ui.find('personal-access-list').children[0].textContent, /VSP-/);
  } finally { ui.cleanup(); }
});

test('named creation displays the returned token, local QR and login link; copy and dismissal clear all secret surfaces', async () => {
  const ui = await mount({isAdmin:true});
  try {
    ui.find('personal-code-label').value = '  Neue Testperson  ';
    await ui.find('create-code-form').emit('submit');
    const request = ui.calls.find(call => call.url.endsWith('/api/access-codes') && call.options.method === 'POST');
    assert.deepEqual(JSON.parse(request.options.body), {label:'Neue Testperson'});
    assert.equal(request.options.headers.get('X-CSRF-Token'), 'test-csrf');
    assert.equal(ui.find('generated-code-label').textContent, 'Neue Testperson');
    assert.equal(ui.find('generated-access-code').value, token);
    assert.equal(ui.find('generated-login-link').value, site + '#access=' + token);
    assert.match(ui.find('generated-qr').src, /^data:image\/svg\+xml,/);
    assert.ok(decodeURIComponent(ui.find('generated-qr').src).includes(site + '#access=' + token));
    assert.match(ui.find('generated-qr').attributes.alt, /Neue Testperson/);
    await ui.find('copy-link-button').emit('click');
    await ui.find('copy-code-button').emit('click');
    assert.deepEqual(ui.copies, [site + '#access=' + token, token]);
    await ui.find('dismiss-code-button').emit('click');
    assert.equal(ui.find('generated-access-code').value, '');
    assert.equal(ui.find('generated-login-link').value, '');
    assert.equal(ui.find('generated-qr').src, '');
    assert.equal(ui.find('generated-code-label').textContent, '');
    assert.equal(ui.find('generated-code-panel').hidden, true);
  } finally { ui.cleanup(); }
});

test('personal sessions cannot create or list codes even through direct UI events', async () => {
  const ui = await mount({isAdmin:'true'});
  try {
    ui.find('personal-code-label').value = 'Unbefugt';
    await ui.find('create-code-form').emit('submit');
    assert.equal(ui.calls.some(call => call.url.endsWith('/api/access-codes')), false);
    assert.equal(ui.find('generated-code-panel').hidden, true);
  } finally { ui.cleanup(); }
});

test('page exit and logout clear generated QR, link, code and name', async () => {
  for (const action of ['pagehide', 'logout']) {
    const ui = await mount({isAdmin:true});
    try {
      ui.find('personal-code-label').value = 'Neue Testperson';
      await ui.find('create-code-form').emit('submit');
      if (action === 'pagehide') ui.listeners.pagehide();
      else await ui.find('logout-button').emit('click');
      assert.equal(ui.find('generated-access-code').value, '');
      assert.equal(ui.find('generated-login-link').value, '');
      assert.equal(ui.find('generated-qr').src, '');
      assert.equal(ui.find('generated-code-label').textContent, '');
      assert.equal(ui.find('generated-code-panel').hidden, true);
    } finally { ui.cleanup(); }
  }
});

test('QR rendering failure still preserves the once-created code and direct login link', async () => {
  const ui = await mount({isAdmin:true, qrAvailable:false});
  try {
    ui.find('personal-code-label').value = 'Neue Testperson';
    await ui.find('create-code-form').emit('submit');
    assert.equal(ui.find('generated-access-code').value, token);
    assert.equal(ui.find('generated-login-link').value, site + '#access=' + token);
    assert.equal(ui.find('generated-code-panel').hidden, false);
    assert.equal(ui.find('generated-qr').hidden, true);
    assert.match(ui.find('code-copy-message').textContent, /QR-Code/);
  } finally { ui.cleanup(); }
});
