#!/usr/bin/env node
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

// Exercise the real UI and recording handlers; only DOM, media and HTTP are faked.
// No browser package, microphone, credentials or network connection is used.
const source = readFileSync(new URL('./web/app.js', import.meta.url), 'utf8');
const html = readFileSync(new URL('./web/index.html', import.meta.url), 'utf8');
const retentionNotice = 'Neue Aufnahmen bleiben gespeichert, bis Sie oder ein Administrator sie löschen.';
const tick = () => new Promise(setImmediate);
let sequence = 0;

class Element {
  constructor(tag, doc) {
    Object.assign(this, {tagName:tag, doc, children:[], listeners:{}, dataset:{}, attributes:{}, style:{}, hidden:false, disabled:false, checked:false, open:false, value:'', src:'', textContent:'', className:'', isConnected:true});
    const classes = new Set();
    this.classList = {add:(...names)=>names.forEach(name=>classes.add(name)), remove:(...names)=>names.forEach(name=>classes.delete(name)), toggle:(name,on)=>on?classes.add(name):classes.delete(name)};
  }
  append(...elements) { this.children.push(...elements); }
  replaceChildren(...elements) { this.children.forEach(child=>{child.isConnected=false;}); this.children=[...elements]; }
  setAttribute(name,value) { this.attributes[name]=String(value); }
  removeAttribute(name) { delete this.attributes[name]; if(name==='src')this.src=''; }
  addEventListener(name,listener) { (this.listeners[name]??=[]).push(listener); }
  async emit(name,event={}) { event.preventDefault??=()=>{}; for(const listener of this.listeners[name]??[])await listener(event); }
  pause() {}
  load() {}
  focus() { if(!this.disabled)this.doc.activeElement=this; }
  select() {}
  showModal() { this.open=true; }
  close() { this.open=false; queueMicrotask(()=>void this.emit('close')); }
  querySelectorAll(selector) { return this.doc.select(this.children,selector); }
}
function createDocument() {
  const doc={elements:[],activeElement:null};
  doc.select=(roots,selector)=>{
    const all=[];const visit=node=>{all.push(node);node.children.forEach(visit);};roots.forEach(visit);
    return [...new Set(all)].filter(element=>selector==='[id]'?Boolean(element.id):selector==='audio'?element.tagName==='audio':selector==='[data-profile-action]'?Boolean(element.dataset.profileAction):selector.startsWith('.')?element.className.split(' ').includes(selector.slice(1)):false);
  };
  doc.querySelectorAll=selector=>doc.select(doc.elements,selector);
  doc.createElement=tag=>new Element(tag,doc);
  for(const match of html.matchAll(/<([\w-]+)\b([^>]*\bid="([^"]+)"[^>]*)>/g)) {
    const element=new Element(match[1],doc);
    Object.assign(element,{id:match[3],hidden:/\bhidden(?:\s|$)/.test(match[2]),disabled:/\bdisabled(?:\s|$)/.test(match[2]),checked:/\bchecked(?:\s|$)/.test(match[2]),className:/\bclass="([^"]*)"/.exec(match[2])?.[1]??''});
    doc.elements.push(element);
  }
  return doc;
}
async function mount({postfair=true,recordingAllowed=true}={}) {
  const doc=createDocument(),find=id=>doc.elements.find(element=>element.id===id);
  const old=Object.fromEntries(['document','window','fetch','navigator','AudioWorkletNode'].map(key=>[key,Object.getOwnPropertyDescriptor(globalThis,key)]));
  const oldCreate=URL.createObjectURL,oldRevoke=URL.revokeObjectURL;
  const calls=[],nodes=[],contexts=[],listeners=[];
  let microphoneRequests=0,selected='synthetic-scc-demo';
  const profiles=[
    {id:'expired-fair',name:'Alte Messeaufnahme',can_delete:true,can_activate:false,owner_is_self:true},
    {id:'postfair-new',name:'Neue Aufnahme',can_delete:true,can_activate:true,owner_is_self:true},
    {id:'synthetic-scc-demo',name:'Standardstimme',can_delete:false,can_activate:true},
  ];
  class AudioContext {
    constructor(){Object.assign(this,{sampleRate:24000,state:'running',audioWorklet:{async addModule(){}},destination:{}});contexts.push(this);}
    createMediaStreamSource(){return {connect(){},disconnect(){}};}
    createGain(){return {gain:{value:0},connect(){},disconnect(){}};}
    async resume(){}
    async close(){this.state='closed';}
  }
  class AudioWorkletNode {
    constructor(){this.port={onmessage:null,postMessage:(command)=>{if(command==='finish')queueMicrotask(()=>this.port.onmessage?.({data:{type:'finished'}}));}};nodes.push(this);}
    connect(){}
    disconnect(){}
  }
  globalThis.document=doc;
  globalThis.window={isSecureContext:true,AudioContext,AudioWorkletNode,addEventListener(name,listener){listeners[name]=listener;}};
  globalThis.AudioWorkletNode=AudioWorkletNode;
  Object.defineProperty(globalThis,'navigator',{configurable:true,value:{mediaDevices:{async getUserMedia(){microphoneRequests++;const track={stop(){},addEventListener(){}};return {getTracks:()=>[track],getAudioTracks:()=>[track]};}}}});
  URL.createObjectURL=()=>`blob:postfair-${sequence++}`;
  URL.revokeObjectURL=()=>{};
  globalThis.fetch=async(url,options={})=>{
    calls.push({url,options});let body;
    if(url.endsWith('/api/session'))body={authenticated:true,csrf:'test-csrf',is_admin:false,label:'Testperson',recording_allowed:recordingAllowed,postfair_mode:postfair,retention_notice:retentionNotice,reference_text:'Ich helfe Ihnen gern, einen Laptop zu bestellen.',max_recording_seconds:25};
    else if(url.endsWith('/api/profiles')&&options.method==='POST')body={profile:{id:'saved-new',name:'Meine Stimme'}};
    else if(url.endsWith('/api/profiles'))body={profiles,selected_profile_id:selected};
    else if(/\/api\/profiles\/[^/]+\/activate$/.test(url)){selected=decodeURIComponent(url.split('/').at(-2));body={selected_profile_id:selected};}
    else if(url.endsWith('/api/logout'))body={};
    else if(url.endsWith('/api/login'))body={csrf:'new-test-csrf'};
    else throw new Error(`Unexpected endpoint: ${url}`);
    return {ok:true,status:200,json:async()=>body};
  };
  const loaded=source.replaceAll('import.meta.url',JSON.stringify('https://studio.test/voice-studio/app.js'))+`\n// isolated postfair instance ${sequence++}`;
  await import('data:text/javascript;base64,'+Buffer.from(loaded).toString('base64'));await tick();
  const action=(profileId,name)=>{
    const index=profiles.findIndex(profile=>profile.id===profileId);
    return find('profile-list').children[index].querySelectorAll('[data-profile-action]').find(button=>button.dataset.profileAction===name);
  };
  async function stopRecording(){await find('stop-button').emit('click');await tick();await tick();}
  return {find,doc,calls,nodes,contexts,listeners,action,get microphoneRequests(){return microphoneRequests;},async capture(){await find('record-button').emit('click');assert.ok(nodes.length,'recording creates an AudioWorklet');nodes.at(-1).port.onmessage({data:{type:'samples',samples:Float32Array.from({length:24000*4},(_,i)=>0.1*Math.sin(i/12))}});await stopRecording();assert.equal(find('recording-preview').hidden,false);},async cleanup(){await stopRecording();for(const [key,descriptor]of Object.entries(old)){if(descriptor)Object.defineProperty(globalThis,key,descriptor);else delete globalThis[key];}URL.createObjectURL=oldCreate;URL.revokeObjectURL=oldRevoke;}};
}
async function prepareNameAndVoiceConsent(ui){ui.find('profile-name').value='Meine Stimme';ui.find('voice-consent').checked=true;await ui.find('profile-name').emit('input');await ui.find('voice-consent').emit('change');}
function retentionCheckbox(ui){const checkbox=ui.find('retention-consent');assert.ok(checkbox,'postfair consent has a separate explicit checkbox');return checkbox;}
const uploads=ui=>ui.calls.filter(call=>call.url.endsWith('/api/profiles')&&call.options.method==='POST');

test('postfair recording needs a separate fresh retention consent before microphone access',async()=>{
  const ui=await mount();
  try {
    const checkbox=retentionCheckbox(ui);
    assert.equal(checkbox.checked,false,'the new retention basis must not be preaccepted');
    assert.ok(html.includes(retentionNotice),'the exact continued-retention notice is visible in the page');
    await prepareNameAndVoiceConsent(ui);
    assert.equal(ui.find('record-button').disabled,true);
    await ui.find('record-button').emit('click');
    assert.equal(ui.microphoneRequests,0,'direct handler invocation must also respect missing consent');
    checkbox.checked=true;await checkbox.emit('change');
    assert.equal(ui.find('record-button').disabled,false);
    await ui.capture();
    assert.equal(ui.microphoneRequests,1);
    assert.equal(ui.find('save-button').disabled,false);
  } finally {await ui.cleanup();}
});

test('saving rechecks retention consent, sends the declared retention basis and clears both consents',async()=>{
  const ui=await mount();
  try {
    const checkbox=retentionCheckbox(ui);
    await prepareNameAndVoiceConsent(ui);checkbox.checked=true;await checkbox.emit('change');
    await ui.capture();
    checkbox.checked=false;await checkbox.emit('change');
    assert.equal(ui.find('save-button').disabled,true);
    await ui.find('save-button').emit('click');
    assert.equal(uploads(ui).length,0,'a recorded sample cannot be saved after consent is withdrawn');
    checkbox.checked=true;await checkbox.emit('change');await ui.find('save-button').emit('click');
    assert.equal(uploads(ui).length,1);
    const request=uploads(ui)[0],payload=JSON.parse(request.options.body);
    assert.equal(request.options.headers.get('X-CSRF-Token'),'test-csrf');
    assert.equal(payload.consent.own_voice,true);
    assert.equal(payload.consent.retention,'until_deleted');
    assert.equal(payload.consent.retention_notice,retentionNotice);
    assert.ok(Number.isFinite(Date.parse(payload.consent.confirmed_at_utc)));
    assert.ok(payload.wav_b64.length>44);
    assert.equal(ui.find('voice-consent').checked,false);
    assert.equal(checkbox.checked,false);
    assert.equal(ui.find('record-button').disabled,true);
  } finally {await ui.cleanup();}
});

test('a postfair session can activate only explicitly eligible profiles while old profiles remain blocked',async()=>{
  const ui=await mount();
  try {
    const old=ui.action('expired-fair','select'),fresh=ui.action('postfair-new','select');
    assert.equal(old.disabled,true);
    assert.equal(fresh.disabled,false);
    await old.emit('click');
    assert.equal(ui.calls.some(call=>call.url.endsWith('/expired-fair/activate')),false,'an old profile remains blocked even when its click handler is invoked directly');
    await fresh.emit('click');
    assert.equal(ui.calls.filter(call=>call.url.endsWith('/postfair-new/activate')).length,1);
    assert.equal(ui.find('active-name').textContent,'Neue Aufnahme');
    assert.equal(ui.action('expired-fair','listen').disabled,false,'old visible metadata does not turn off listening');
    assert.equal(ui.action('expired-fair','delete').disabled,false,'old profiles remain deletable');
  } finally {await ui.cleanup();}
});

test('logout clears old ownership and retention acceptance before another personal session',async()=>{
  const ui=await mount();
  try {
    const checkbox=retentionCheckbox(ui);await prepareNameAndVoiceConsent(ui);checkbox.checked=true;await checkbox.emit('change');
    await ui.find('logout-button').emit('click');
    assert.equal(ui.find('voice-consent').checked,false);
    assert.equal(checkbox.checked,false);
    ui.find('access-code').value='synthetic-test-code';await ui.find('login-form').emit('submit');
    ui.find('profile-name').value='Andere Person';await ui.find('profile-name').emit('input');
    assert.equal(ui.find('record-button').disabled,true);
  } finally {await ui.cleanup();}
});

test('fair mode retains the original recording consent contract without requiring postfair acceptance',async()=>{
  const ui=await mount({postfair:false});
  try {
    const checkbox=retentionCheckbox(ui);assert.equal(checkbox.checked,false);
    await prepareNameAndVoiceConsent(ui);
    assert.equal(ui.find('record-button').disabled,false,'the separate retention acceptance applies only to postfair sessions');
    await ui.capture();await ui.find('save-button').emit('click');
    assert.equal(uploads(ui).length,1);
    assert.equal(JSON.parse(uploads(ui)[0].options.body).consent.retention,undefined,'ordinary fair consent is not relabelled as indefinite retention');
  } finally {await ui.cleanup();}
});

test('server-side closed campaign still blocks postfair microphone access',async()=>{
  const ui=await mount({postfair:true,recordingAllowed:false});
  try {
    const checkbox=retentionCheckbox(ui);await prepareNameAndVoiceConsent(ui);checkbox.checked=true;await checkbox.emit('change');
    assert.equal(ui.find('record-button').disabled,true);
    await ui.find('record-button').emit('click');
    assert.equal(ui.microphoneRequests,0);
    assert.equal(uploads(ui).length,0);
  } finally {await ui.cleanup();}
});
