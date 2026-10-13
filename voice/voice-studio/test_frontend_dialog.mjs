#!/usr/bin/env node
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
// Exercise the real UI handlers with a minimal DOM and a controlled HTTP transport.
// These tests send no requests, use no real credentials and require no browser packages.
const source=readFileSync(new URL('./web/app.js',import.meta.url),'utf8');
const html=readFileSync(new URL('./web/index.html',import.meta.url),'utf8');
let sequence=0;
class Element {
  constructor(tag,doc) {this.tagName=tag;this.doc=doc;this.children=[];this.listeners={};this.dataset={};this.attributes={};this.style={};this.hidden=false;this.disabled=false;this.open=false;this.value='';this.src='';this.textContent='';this.className='';this.isConnected=true;const classes=new Set();this.classList={add:(...names)=>names.forEach(name=>classes.add(name)),remove:(...names)=>names.forEach(name=>classes.delete(name)),toggle:(name,on)=>on?classes.add(name):classes.delete(name),contains:name=>classes.has(name)};}
  append(...elements){this.children.push(...elements);}
  replaceChildren(...elements){for(const child of this.children)child.isConnected=false;this.children=[...elements];}
  setAttribute(name,value){this.attributes[name]=value;}
  removeAttribute(name){delete this.attributes[name];if(name==='src')this.src='';}
  addEventListener(name,listener){(this.listeners[name]??=[]).push(listener);}
  async emit(name,event={}){event.preventDefault??=()=>{};for(const listener of this.listeners[name]??[])await listener(event);}
  pause(){this.paused=true;}
  load(){}
  focus(){if(!this.disabled)this.doc.activeElement=this;}
  select(){}
  showModal(){this.open=true;}
  close(){this.open=false;queueMicrotask(()=>void this.emit('close'));}
  querySelectorAll(selector){return this.doc.select(this.children,selector);}
}
function createDocument(){
  const doc={elements:[],activeElement:null};
  doc.select=(roots,selector)=>{
    const all=[];const visit=node=>{all.push(node);node.children.forEach(visit)};roots.forEach(visit);
    return [...new Set(all)].filter(element=>selector==='[id]'?Boolean(element.id):selector==='audio'?element.tagName==='audio':selector==='[data-profile-action]'?Boolean(element.dataset.profileAction):selector.startsWith('.')?element.className.split(' ').includes(selector.slice(1)):false);
  };
  doc.querySelectorAll=selector=>doc.select(doc.elements,selector);
  doc.createElement=tag=>new Element(tag,doc);
  for(const match of html.matchAll(/<([\w-]+)\b([^>]*\bid="([^"]+)"[^>]*)>/g)){
    const element=new Element(match[1],doc);element.id=match[3];element.hidden=/\bhidden(?:\s|$)/.test(match[2]);element.disabled=/\bdisabled(?:\s|$)/.test(match[2]);element.className=/\bclass="([^"]*)"/.exec(match[2])?.[1]??'';doc.elements.push(element);
  }
  return doc;
}
async function mount({deleteStatus=403,deleteCode='delete_confirmation_rejected',refreshFails=false,isAdmin=false,recordingAllowed=true,includeDefault=false}={}){
  const doc=createDocument();const find=id=>doc.elements.find(element=>element.id===id);let deleted=false;const calls=[];
  const old={document:globalThis.document,window:globalThis.window,fetch:globalThis.fetch};
  globalThis.document=doc;globalThis.window={addEventListener(){}};
  globalThis.fetch=async(url,options={})=>{
    calls.push({url,options});
    let status=200;let body;
    if(url.endsWith('/api/session'))body={authenticated:true,is_admin:isAdmin,principal_id:'test-owner',label:'Testperson',csrf:'test-csrf',recording_allowed:recordingAllowed,reference_text:'Ein deutscher Testtext.',max_recording_seconds:25};
    else if(url.endsWith('/api/access-codes')&&options.method==='POST'){status=201;body={access_code:{id:'new-owner',label:'Neue Testperson'},code:'VSP-0123456789abcdef-abcdefghijklmnopqrstuvwx'};}
    else if(url.endsWith('/api/access-codes'))body={access_codes:[]};
    else if(url.endsWith('/api/logout'))body={};
    else if(options.method==='DELETE'){status=deleteStatus;body=status<400?{id:'owned',deleted:true}:{error:deleteCode==='delete_purge_failed'?'Die Stimme wurde entfernt, konnte aber nicht vollständig gelöscht werden. Bitte den Administrator kontaktieren.':deleteCode==='delete_finalize_failed'?'Die Aufnahme wurde gelöscht, aber die Abschlussbestätigung ist fehlgeschlagen. Bitte den Administrator informieren.':'Der Zugangscode ist ungültig.',code:deleteCode};if(status<400||['delete_purge_failed','delete_finalize_failed'].includes(deleteCode))deleted=true;}
    else if(url.endsWith('/api/profiles')){if(deleted&&refreshFails){status=503;body={error:'Die Liste ist vorübergehend nicht erreichbar.'};}else body={profiles:[...(deleted?[]:[{id:'owned',name:'Exakter Profilname',can_delete:true,owner_is_self:true,duration_seconds:4,created_at_utc:'2026-10-13T10:00:00Z'}]),...(includeDefault?[{id:'synthetic-scc-demo',name:'Standardstimme',can_delete:false}]:[])],selected_profile_id:'another'};}
    else throw new Error('Unexpected endpoint');
    return {ok:status<400,status,json:async()=>body};
  };
  const loaded=source.replaceAll('import.meta.url',JSON.stringify('https://studio.test/voice-studio/app.js'))+`\n// isolated UI instance ${sequence++}`;
  await import('data:text/javascript;base64,'+Buffer.from(loaded).toString('base64'));
  await new Promise(setImmediate);
  const remove=doc.querySelectorAll('[data-profile-action]').find(element=>element.dataset.profileAction==='delete');
  assert.ok(remove,'owned profile exposes a delete control');
  return {doc,find,calls,remove,cleanup(){globalThis.document=old.document;globalThis.window=old.window;globalThis.fetch=old.fetch;}};
}

test('server-denied deletion keeps the exact-name dialog usable, clears the code and focuses it',async()=>{
  const ui=await mount();
  try{
    await ui.remove.emit('click');
    assert.equal(ui.find('delete-dialog').open,true);
    assert.equal(ui.find('delete-profile-name').textContent,'Exakter Profilname');
    ui.find('delete-access-code').value='test-owned-code';
    await ui.find('delete-form').emit('submit');
    assert.equal(ui.find('delete-dialog').open,true);
    assert.equal(ui.find('delete-access-code').value,'');
    assert.equal(ui.find('delete-message').textContent,'Der Zugangscode ist ungültig.');
    assert.equal(ui.find('delete-message').hidden,false);
    assert.equal(ui.doc.activeElement,ui.find('delete-access-code'));
    assert.equal(ui.find('delete-access-code').disabled,false);
    assert.equal(ui.find('delete-confirm-button').disabled,false);
    assert.equal(ui.find('profile-list').children.length,1);
    const request=ui.calls.find(call=>call.options.method==='DELETE');
    assert.ok(request.url.endsWith('/api/profiles/owned'));
    assert.equal(request.options.headers.get('X-CSRF-Token'),'test-csrf');
    assert.deepEqual(JSON.parse(request.options.body),{password:'test-owned-code'});
  }finally{ui.cleanup();}
});

test('cancel closes deletion without sending a request and clears the confirmation code',async()=>{
  const ui=await mount();
  try{
    await ui.remove.emit('click');ui.find('delete-access-code').value='do-not-send';
    await ui.find('delete-cancel-button').emit('click');await new Promise(setImmediate);
    assert.equal(ui.find('delete-dialog').open,false);
    assert.equal(ui.find('delete-access-code').value,'');
    assert.equal(ui.calls.some(call=>call.options.method==='DELETE'),false);
    assert.equal(ui.doc.activeElement,ui.remove);
  }finally{ui.cleanup();}
});

test('confirmed deletion reports a subsequent refresh failure honestly and clears the dialog',async()=>{
  const ui=await mount({deleteStatus:200,refreshFails:true});
  try{
    await ui.remove.emit('click');ui.find('delete-access-code').value='test-owned-code';
    await ui.find('delete-form').emit('submit');await new Promise(setImmediate);
    assert.equal(ui.find('delete-dialog').open,false);
    assert.equal(ui.find('delete-access-code').value,'');
    assert.match(ui.find('page-message').textContent,/wurde dauerhaft gelöscht/);
    assert.match(ui.find('page-message').textContent,/Liste konnte nicht aktualisiert werden/);
    assert.equal(ui.doc.querySelectorAll('[data-profile-action]').some(button=>button.dataset.profileAction==='delete'),false);
    assert.equal(ui.doc.activeElement,ui.find('refresh-button'));
  }finally{ui.cleanup();}
});

test('a failed physical purge refreshes the list and reports incomplete deletion without success',async()=>{
  const ui=await mount({deleteStatus:503,deleteCode:'delete_purge_failed'});
  try{
    await ui.remove.emit('click');ui.find('delete-access-code').value='test-owned-code';
    await ui.find('delete-form').emit('submit');await new Promise(setImmediate);
    assert.equal(ui.find('delete-dialog').open,false);
    assert.equal(ui.find('delete-access-code').value,'');
    assert.match(ui.find('page-message').textContent,/nicht vollständig gelöscht/);
    assert.doesNotMatch(ui.find('page-message').textContent,/wurde dauerhaft gelöscht/);
    assert.equal(ui.doc.querySelectorAll('[data-profile-action]').some(button=>button.dataset.profileAction==='delete'),false);
    assert.equal(ui.doc.activeElement,ui.find('refresh-button'));
  }finally{ui.cleanup();}
});

test('failed completion confirmation clears the removed profile and reports the exact error',async()=>{
  const ui=await mount({deleteStatus:503,deleteCode:'delete_finalize_failed'});
  try{
    await ui.remove.emit('click');ui.find('delete-access-code').value='test-owned-code';
    await ui.find('delete-form').emit('submit');await new Promise(setImmediate);
    assert.equal(ui.find('delete-dialog').open,false);
    assert.equal(ui.find('delete-access-code').value,'');
    assert.match(ui.find('page-message').textContent,/Abschlussbestätigung ist fehlgeschlagen/);
    assert.doesNotMatch(ui.find('page-message').textContent,/wurde dauerhaft gelöscht/);
    assert.equal(ui.doc.querySelectorAll('[data-profile-action]').some(button=>button.dataset.profileAction==='delete'),false);
    assert.equal(ui.doc.activeElement,ui.find('refresh-button'));
    assert.equal(ui.calls.filter(call=>call.url.endsWith('/api/profiles')&&!call.options.method).length,2);
  }finally{ui.cleanup();}
});

test('a session without explicit administrator status hides code creation and sends no creation request',async()=>{
  const ui=await mount({isAdmin:'true'});
  try{
    assert.equal(ui.find('admin-panel').hidden,true);
    ui.find('personal-code-label').value='Unbefugte Codeerstellung';
    await ui.find('create-code-form').emit('submit');
    assert.equal(ui.calls.some(call=>call.url.endsWith('/api/access-codes')),false);
    assert.equal(ui.find('generated-access-code').value,'');
    assert.equal(ui.find('generated-code-panel').hidden,true);
  }finally{ui.cleanup();}
});

test('an administrator sees the new code once and dismissal or logout clears it',async()=>{
  const ui=await mount({isAdmin:true});
  try{
    assert.equal(ui.find('admin-panel').hidden,false);
    ui.find('personal-code-label').value='Neue Testperson';
    await ui.find('create-code-form').emit('submit');
    assert.equal(ui.find('generated-access-code').value,'VSP-0123456789abcdef-abcdefghijklmnopqrstuvwx');
    assert.equal(ui.find('generated-code-panel').hidden,false);
    assert.equal(ui.find('copy-code-button').disabled,false);
    await ui.find('dismiss-code-button').emit('click');
    assert.equal(ui.find('generated-access-code').value,'');
    assert.equal(ui.find('generated-code-panel').hidden,true);
    ui.find('personal-code-label').value='Neue Testperson';
    await ui.find('create-code-form').emit('submit');
    await ui.find('logout-button').emit('click');
    assert.equal(ui.find('generated-access-code').value,'');
    assert.equal(ui.find('generated-code-panel').hidden,true);
    assert.equal(ui.find('admin-panel').hidden,true);
    assert.equal(ui.find('session-label').hidden,true);
    assert.equal(ui.find('login-view').hidden,false);
  }finally{ui.cleanup();}
});

test('an expired demo blocks recording and own-voice selection but preserves listening, deletion and default selection',async()=>{
  const ui=await mount({recordingAllowed:false,includeDefault:true});
  try{
    ui.find('profile-name').value='Meine neue Stimme';ui.find('voice-consent').checked=true;
    await ui.find('profile-name').emit('input');
    assert.equal(ui.find('record-button').disabled,true);
    assert.equal(ui.find('retention-message').hidden,false);
    const profiles=ui.find('profile-list').children;
    const actions=profile=>profile.querySelectorAll('[data-profile-action]');
    assert.equal(actions(profiles[0]).find(button=>button.dataset.profileAction==='select').disabled,true);
    assert.equal(actions(profiles[0]).find(button=>button.dataset.profileAction==='listen').disabled,false);
    assert.equal(actions(profiles[0]).find(button=>button.dataset.profileAction==='delete').disabled,false);
    assert.equal(actions(profiles[1]).find(button=>button.dataset.profileAction==='select').disabled,false);
  }finally{ui.cleanup();}
});
