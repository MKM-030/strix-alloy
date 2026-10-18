#!/usr/bin/env node
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

// Run the real event handlers. Only browser DOM/media and the HTTP boundary are simulated.
const source = readFileSync(new URL('./web/app.js', import.meta.url), 'utf8');
const html = readFileSync(new URL('./web/index.html', import.meta.url), 'utf8');
const tick = () => new Promise(setImmediate);
let sequence = 0;
class Element {
  constructor(tag, doc) {
    Object.assign(this, {tagName:tag, doc, children:[], listeners:{}, dataset:{}, attributes:{}, style:{}, hidden:false, disabled:false, open:false, value:'', src:'', textContent:'', className:'', isConnected:true, paused:true, plays:0});
    const classes = new Set();
    this.classList = {add:(...names)=>names.forEach(name=>classes.add(name)), remove:(...names)=>names.forEach(name=>classes.delete(name)), toggle:(name,on)=>on?classes.add(name):classes.delete(name)};
  }
  append(...elements) { this.children.push(...elements); }
  replaceChildren(...elements) { this.children.forEach(child=>{child.isConnected=false;}); this.children=[...elements]; }
  setAttribute(name, value) { this.attributes[name]=value; }
  removeAttribute(name) { delete this.attributes[name]; if (name==='src') this.src=''; }
  addEventListener(name, listener) { (this.listeners[name]??=[]).push(listener); }
  async emit(name, event={}) { event.preventDefault??=()=>{}; for (const listener of this.listeners[name]??[]) await listener(event); }
  pause() { this.paused=true; }
  async play() { this.paused=false; this.plays++; await this.emit('play'); }
  load() {}
  focus() { if (!this.disabled) this.doc.activeElement=this; }
  select() {}
  showModal() { this.open=true; }
  close() { this.open=false; queueMicrotask(()=>void this.emit('close')); }
  querySelectorAll(selector) { return this.doc.select(this.children, selector); }
}
function createDocument() {
  const doc={elements:[], activeElement:null};
  doc.select=(roots,selector)=>{
    const all=[]; const visit=node=>{all.push(node); node.children.forEach(visit);}; roots.forEach(visit);
    return all.filter(element=>selector==='[id]'?Boolean(element.id):selector==='audio'?element.tagName==='audio':selector==='[data-profile-action]'?Boolean(element.dataset.profileAction):selector.startsWith('.')?element.className.split(' ').includes(selector.slice(1)):false);
  };
  doc.querySelectorAll=selector=>doc.select(doc.elements,selector);
  doc.createElement=tag=>new Element(tag,doc);
  for (const match of html.matchAll(/<([\w-]+)\b([^>]*\bid="([^"]+)"[^>]*)>/g)) {
    const element=new Element(match[1],doc);
    Object.assign(element,{id:match[3],hidden:/\bhidden(?:\s|$)/.test(match[2]),disabled:/\bdisabled(?:\s|$)/.test(match[2]),className:/\bclass="([^"]*)"/.exec(match[2])?.[1]??''});
    doc.elements.push(element);
  }
  return doc;
}
function deferred() { let resolve,reject; const promise=new Promise((yes,no)=>{resolve=yes;reject=no;}); return {promise,resolve,reject}; }
const wav = () => ({ok:true,status:200,blob:async()=>new Blob(['RIFF-test-wave'],{type:'audio/wav'})});
async function mount({preview=async()=>wav(),recordingAllowed=true,microphone}={}) {
  const doc=createDocument(); const find=id=>doc.elements.find(element=>element.id===id); const calls=[],listeners={},created=[],revoked=[];
  const old=Object.fromEntries(['document','window','fetch','navigator'].map(key=>[key,Object.getOwnPropertyDescriptor(globalThis,key)]));
  const oldCreate=URL.createObjectURL, oldRevoke=URL.revokeObjectURL;
  globalThis.document=doc;
  globalThis.window={isSecureContext:true,addEventListener(name,listener){listeners[name]=listener;}};
  if (microphone) { globalThis.window.AudioContext=class {}; globalThis.window.AudioWorkletNode=class {}; }
  Object.defineProperty(globalThis,'navigator',{configurable:true,value:{mediaDevices:{getUserMedia(){if(microphone)return microphone();throw new Error('Mikrofon darf während der Vorschau nicht gestartet werden.');}}}});
  URL.createObjectURL=blob=>{const url=`blob:preview-${created.length}`;created.push({url,blob});return url;};
  URL.revokeObjectURL=url=>revoked.push(url);
  globalThis.fetch=async(url,options={})=>{
    calls.push({url,options}); let body;
    if (url.endsWith('/api/session')) body={authenticated:true,csrf:'test-csrf',reference_text:'Ein deutscher Testtext.',recording_allowed:recordingAllowed};
    else if (url.endsWith('/api/profiles')) body={profiles:[{id:'owned/ä',name:'Exakter <Profilname>',can_delete:true},{id:'synthetic-scc-demo',name:'SCC Standardstimme',can_delete:false}],selected_profile_id:'synthetic-scc-demo'};
    else if (/\/api\/profiles\/[^/]+\/preview$/.test(url)||url.endsWith('/api/preview')) return preview(url,options);
    else if (url.endsWith('/api/login')) body={csrf:'new-test-csrf'};
    else if (url.endsWith('/api/logout')) body={};
    else throw new Error(`Unexpected endpoint: ${url}`);
    return {ok:true,status:200,json:async()=>body};
  };
  const loaded=source.replaceAll('import.meta.url',JSON.stringify('https://studio.test/voice-studio/app.js'))+`\n// isolated preview instance ${sequence++}`;
  await import('data:text/javascript;base64,'+Buffer.from(loaded).toString('base64')); await tick();
  const buttons=()=>doc.querySelectorAll('[data-profile-action]').filter(button=>button.dataset.profileAction==='preview');
  return {doc,find,calls,listeners,created,revoked,buttons,cleanup(){for(const [key,descriptor] of Object.entries(old)){if(descriptor)Object.defineProperty(globalThis,key,descriptor);else delete globalThis[key];}URL.createObjectURL=oldCreate;URL.revokeObjectURL=oldRevoke;}};
}

test('every profile including the selected default opens an editable exact-name preview dialog',async()=>{
  const ui=await mount({recordingAllowed:false});
  try {
    assert.equal(ui.buttons().length,2,'each profile needs its own synthesized preview control');
    assert.equal(ui.buttons()[1].disabled,false,'preview is independent of selection and retention');
    assert.match(ui.buttons()[0].textContent,/Beispieltext anhören/);
    await ui.buttons()[0].emit('click');
    assert.equal(ui.find('preview-dialog').open,true);
    assert.equal(ui.find('preview-profile-name').textContent,'Exakter <Profilname>');
    const input=ui.find('preview-text');
    assert.equal(input.tagName,'textarea');
    assert.ok(input.value.length>=90&&input.value.length<=220,'the preset is long enough for a useful comparison');
    assert.match(input.value,/Sopra Steria/); assert.match(input.value,/ServiceNow/); assert.match(input.value,/Laptop/);
    assert.equal(input.disabled,false); assert.equal(ui.doc.activeElement,input);
    assert.match(html,/id="preview-text"[^>]*maxlength="300"/);
  } finally {ui.cleanup();}
});

test('edited text requests only that profile with CSRF and produces playable WAV inside the dialog',async()=>{
  const ui=await mount();
  try {
    await ui.buttons()[0].emit('click');ui.find('preview-text').value='  Guten Tag. Ich bestelle einen neuen Laptop für Ihren Mitarbeiter.  ';
    await ui.find('preview-form').emit('submit');
    const request=ui.calls.find(call=>call.options.method==='POST');
    assert.ok(request.url.endsWith('/api/profiles/owned%2F%C3%A4/preview'));
    assert.equal(request.options.headers.get('X-CSRF-Token'),'test-csrf');
    assert.equal(request.options.headers.get('Content-Type'),'application/json');
    assert.equal(request.options.credentials,'same-origin'); assert.equal(request.options.cache,'no-store');
    assert.deepEqual(JSON.parse(request.options.body),{text:'Guten Tag. Ich bestelle einen neuen Laptop für Ihren Mitarbeiter.'});
    assert.equal(ui.calls.some(call=>call.url.endsWith('/activate')),false);
    assert.equal(ui.find('active-name').textContent,'SCC Standardstimme');
    const audio=ui.find('preview-audio');assert.equal(audio.src,'blob:preview-0');assert.equal(audio.hidden,false);assert.equal(audio.plays,1);
    assert.equal(ui.created[0].blob.type,'audio/wav');
  } finally {ui.cleanup();}
});

test('empty or oversized text stays editable without a synthesis request',async()=>{
  const ui=await mount();
  try {
    await ui.buttons()[0].emit('click');
    for (const text of ['   ','a','ab','a'.repeat(301)]) {
      ui.find('preview-text').value=text;await ui.find('preview-form').emit('submit');
      assert.equal(ui.calls.some(call=>call.options.method==='POST'),false);
      assert.equal(ui.find('preview-message').hidden,false);assert.equal(ui.doc.activeElement,ui.find('preview-text'));
    }
  } finally {ui.cleanup();}
});

test('in-flight generation locks recording and duplicate generation while allowing dialog dismissal',async()=>{
  const pending=deferred(); const ui=await mount({preview:()=>pending.promise});
  try {
    ui.find('profile-name').value='Name';ui.find('voice-consent').checked=true;await ui.find('profile-name').emit('input');
    await ui.buttons()[0].emit('click');const work=ui.find('preview-form').emit('submit');await tick();
    assert.equal(ui.find('record-button').disabled,true);assert.equal(ui.find('save-button').disabled,true);
    assert.equal(ui.find('preview-read-button').disabled,true);assert.equal(ui.find('preview-text').disabled,true);
    assert.equal(ui.find('preview-close-button').disabled,false);assert.match(ui.find('preview-message').textContent,/erstellt/);
    await ui.find('preview-form').emit('submit');await ui.find('record-button').emit('click');
    assert.equal(ui.calls.filter(call=>call.options.method==='POST').length,1);
    pending.resolve(wav());await work;
    assert.equal(ui.find('record-button').disabled,true,'the modal keeps recording unavailable');assert.equal(ui.find('preview-read-button').disabled,false);
    await ui.find('preview-close-button').emit('click');await tick();assert.equal(ui.find('record-button').disabled,false);
  } finally {ui.cleanup();}
});

test('closing an in-flight dialog lets the server finish and discards its late audio',async()=>{
  const pending=deferred();const ui=await mount({preview:()=>pending.promise});
  try {
    const button=ui.buttons()[0];await button.emit('click');const work=ui.find('preview-form').emit('submit');await tick();
    await ui.find('preview-close-button').emit('click');await tick();
    assert.equal(ui.find('preview-dialog').open,false);assert.equal(ui.find('preview-audio').src,'');
    const request=ui.calls.find(call=>call.options.method==='POST');assert.equal(request.options.signal,undefined,'closing does not abort shared synthesis');
    pending.resolve(wav());await work;
    assert.equal(ui.created.length,0);assert.equal(ui.find('preview-audio').plays,0);assert.equal(ui.doc.activeElement,button);
    await ui.buttons()[1].emit('click');assert.equal(ui.find('preview-profile-name').textContent,'SCC Standardstimme');assert.equal(ui.find('preview-audio').src,'');
  } finally {ui.cleanup();}
});

test('regeneration and dialog dismissal revoke previous WAV URLs and pause all other audio',async()=>{
  const ui=await mount();
  try {
    await ui.buttons()[0].emit('click');await ui.find('preview-form').emit('submit');
    const original=ui.doc.querySelectorAll('.profile-audio')[0];await original.play();assert.equal(ui.find('preview-audio').paused,true);
    await ui.find('preview-form').emit('submit');assert.equal(original.paused,true);
    assert.deepEqual(ui.revoked,['blob:preview-0']);
    await ui.find('preview-close-button').emit('click');await tick();
    assert.deepEqual(ui.revoked,['blob:preview-0','blob:preview-1']);assert.equal(ui.find('preview-audio').src,'');
  } finally {ui.cleanup();}
});

test('busy and network errors remain German and keep the dialog available for retry',async()=>{
  let offline=false;const ui=await mount({preview:async()=>{if(offline)throw new TypeError('Failed to fetch');return {ok:false,status:409,json:async()=>({error:'Es läuft noch ein Gespräch. Bitte warten Sie.',code:'call_in_progress'})};}});
  try {
    await ui.buttons()[0].emit('click');await ui.find('preview-form').emit('submit');
    assert.equal(ui.find('preview-message').textContent,'Es läuft noch ein Gespräch. Bitte warten Sie.');
    assert.equal(ui.find('preview-dialog').open,true);assert.equal(ui.find('preview-text').disabled,false);assert.equal(ui.find('preview-read-button').disabled,false);
    offline=true;await ui.find('preview-form').emit('submit');assert.match(ui.find('preview-message').textContent,/Sprachdienst.*nicht erreichbar/);
    assert.equal(ui.created.length,0);
  } finally {ui.cleanup();}
});

test('logout and page exit discard pending preview responses without restoring audio or stale messages',async()=>{
  for (const action of ['logout','pagehide']) {
    const pending=deferred();const ui=await mount({preview:()=>pending.promise});
    try {
      await ui.buttons()[0].emit('click');const work=ui.find('preview-form').emit('submit');await tick();
      if(action==='logout')await ui.find('logout-button').emit('click');else ui.listeners.pagehide();
      await tick();pending.resolve(wav());await work;
      assert.equal(ui.find('preview-dialog').open,false);assert.equal(ui.find('preview-audio').src,'');assert.equal(ui.created.length,0);
      assert.equal(ui.find('preview-message').textContent,'');
    } finally {ui.cleanup();}
  }
});

test('the selected-voice header retains one-click playback using the longer profile-specific text',async()=>{
  const ui=await mount();
  try {
    await ui.find('active-preview-button').emit('click');
    const request=ui.calls.find(call=>call.options.method==='POST');assert.ok(request.url.endsWith('/api/profiles/synthetic-scc-demo/preview'));
    assert.ok(JSON.parse(request.options.body).text.length>=90);assert.equal(ui.find('active-preview-audio').plays,1);assert.equal(ui.find('active-preview-audio').hidden,false);
    assert.equal(ui.find('preview-dialog').open,false);
  } finally {ui.cleanup();}
});

test('a queued close event from the previous dialog cannot clear a newly opened profile',async()=>{
  const ui=await mount();
  try {
    await ui.buttons()[0].emit('click');
    ui.find('preview-dialog').close();
    // Native close events can be queued after the next profile is opened.
    await ui.buttons()[1].emit('click');await tick();
    assert.equal(ui.find('preview-dialog').open,true);
    assert.equal(ui.find('preview-profile-name').textContent,'SCC Standardstimme');
    assert.ok(ui.find('preview-text').value.length>=90);
  } finally {ui.cleanup();}
});

test('a current expired session closes its preview and reports the German session error',async()=>{
  const ui=await mount({preview:async()=>({ok:false,status:401,json:async()=>({error:'Ihre Sitzung ist abgelaufen. Bitte melden Sie sich erneut an.'})})});
  try {
    await ui.buttons()[0].emit('click');await ui.find('preview-form').emit('submit');await tick();
    assert.equal(ui.find('preview-dialog').open,false);assert.equal(ui.find('login-view').hidden,false);
    assert.equal(ui.find('page-message').textContent,'Ihre Sitzung ist abgelaufen. Bitte melden Sie sich erneut an.');
  } finally {ui.cleanup();}
});

test('an old unauthorized preview response cannot log out a newly authenticated session',async()=>{
  const pending=deferred();const ui=await mount({preview:()=>pending.promise});
  try {
    await ui.buttons()[0].emit('click');const work=ui.find('preview-form').emit('submit');await tick();
    await ui.find('logout-button').emit('click');await tick();
    ui.find('access-code').value='synthetic-new-session-code';await ui.find('login-form').emit('submit');
    assert.equal(ui.find('studio-view').hidden,false);
    pending.resolve({ok:false,status:401,json:async()=>({error:'Alte Sitzung abgelaufen.'})});await work;await tick();
    assert.equal(ui.find('studio-view').hidden,false);assert.equal(ui.find('login-view').hidden,true);
    assert.notEqual(ui.find('page-message').textContent,'Alte Sitzung abgelaufen.');assert.equal(ui.created.length,0);
  } finally {ui.cleanup();}
});

test('a failed WAV stream shows a German error and re-enables retry',async()=>{
  const ui=await mount({preview:async()=>({ok:true,status:200,blob:async()=>{throw new TypeError('terminated');}})});
  try {
    await ui.buttons()[0].emit('click');await ui.find('preview-form').emit('submit');
    assert.match(ui.find('preview-message').textContent,/Sprachdienst.*nicht erreichbar/);
    assert.equal(ui.find('preview-read-button').disabled,false);assert.equal(ui.created.length,0);
  } finally {ui.cleanup();}
});

test('pending microphone permission prevents preview requests and pauses attempted audio playback',async()=>{
  const permission=deferred();const ui=await mount({microphone:()=>permission.promise});
  try {
    ui.find('profile-name').value='Teststimme';ui.find('voice-consent').checked=true;await ui.find('profile-name').emit('input');
    const work=ui.find('record-button').emit('click');await tick();
    assert.equal(ui.find('active-preview-button').disabled,true);assert.ok(ui.buttons().every(button=>button.disabled));
    const audio=ui.doc.querySelectorAll('.profile-audio')[0];await audio.play();assert.equal(audio.paused,true);
    await ui.buttons()[0].emit('click');await ui.find('active-preview-button').emit('click');
    assert.equal(ui.find('preview-dialog').open,false);assert.equal(ui.calls.some(call=>call.options.method==='POST'),false);
    permission.reject(Object.assign(new Error('denied'),{name:'NotAllowedError'}));await work;
    assert.equal(ui.find('active-preview-button').disabled,false);assert.match(ui.find('record-message').textContent,/Mikrofonzugriff wurde nicht erlaubt/);
  } finally {ui.cleanup();}
});
