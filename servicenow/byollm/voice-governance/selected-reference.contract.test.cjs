'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const clone = value => JSON.parse(JSON.stringify(value));
const descriptor = JSON.parse(fs.readFileSync(path.join(__dirname,'reference-descriptor.v1.example.json'),'utf8'));
const helperSource = fs.readFileSync(path.join(__dirname,'../voice-policy/LocalLLMVoiceAssistantSettings.js'),'utf8');
const resourceSource = fs.readFileSync(path.join(__dirname,'../voice-auth/Authorized-agents-resource.js'),'utf8');
const actor = 'a'.repeat(32), agent = 'b'.repeat(32);

function helperFixture(options = {}) {
  const reference = clone(descriptor);
  const rows = {
    sn_voice_tts_config: [{sys_id:reference.tts_config_sys_id,active:'true',language:'de',voice_id:reference.voice_id,
      parameters:JSON.stringify({scc:{engine:'local_qwen3_tts',localOnly:true,profileId:reference.provenance.profile_id,
        referenceSha256:reference.sha256,reference}}),sys_updated_on:'2026-11-06 12:00:00',sys_mod_count:'3'}],
    sn_voice_language_config: [{sys_id:'c'.repeat(32),deployment:reference.service_id,active:'true',tts_config:reference.tts_config_sys_id}],
    sys_attachment: [{sys_id:reference.attachment_sys_id,table_name:'sn_voice_tts_config',table_sys_id:reference.tts_config_sys_id,
      size_bytes:String(reference.size_bytes),content_type:'audio/vnd.wave',file_name:'approved.wav',sys_updated_on:'2026-11-06 12:00:00',sys_mod_count:'1'}]
  };
  const reads = [], streams = [];
  let currentActor = actor;
  class SecureRecord {
    constructor(table) { this.table=table; this.filters=[]; this.index=-1; this.row=null; }
    isValid() { return Object.hasOwn(rows,this.table); }
    isValidField(field) { return !(options.invalidField && options.invalidField.table===this.table && options.invalidField.field===field); }
    get(id) { this.row=rows[this.table].find(row => row.sys_id===id); return !!this.row; }
    getUniqueValue() { return this.row.sys_id; }
    getRecordClassName() { return this.table; }
    canRead() { return options.deniedRow!==this.table; }
    getElement(field) { return {canRead:() => !(options.deniedField && options.deniedField.table===this.table && options.deniedField.field===field)}; }
    getValue(field) { reads.push({table:this.table,field}); return this.row[field]; }
    addQuery(field,value) { this.filters.push([field,String(value)]); }
    setLimit(value) { this.limit=value; }
    query() { this.matches=rows[this.table].filter(row => this.filters.every(([field,value]) => String(row[field])===value)).slice(0,this.limit); }
    next() { this.row=this.matches[++this.index]; return !!this.row; }
  }
  const context = {
    Class:{create:() => function(){ if(this.initialize) this.initialize(); }},
    GlideRecordSecure:SecureRecord,
    GlideSysAttachment:function(){ this.getContentStream=id => {const value={id,open:streams.length+1};streams.push(value);return value;}; },
    GlideDigest:function(){ this.getSHA256HexFromInputStream=stream => {
      assert.equal(stream.id,reference.attachment_sys_id);
      if(options.onDigest) options.onDigest({rows,setActor:value => {currentActor=value;}});
      return options.digest || reference.sha256;
    }; },
    gs:{getUserID:() => currentActor,getUserName:() => 'approved.caller'}
  };
  vm.createContext(context); vm.runInContext(helperSource,context,{filename:'LocalLLMVoiceAssistantSettings.candidate.js'});
  const helper = new context.LocalLLMVoiceAssistantSettings();
  helper.getSettings = serviceId => {
    const voices={de:{voice_id:rows.sn_voice_tts_config[0].voice_id,voice_gender:'male'}};
    helper._voiceReferences(serviceId,reference.tts_config_sys_id,voices);
    return {tts:{voices}};
  };
  return {helper,reference,rows,reads,streams};
}

test('selected projection binds the native locale and reopens only after digest verification', () => {
  const f=helperFixture();
  const projected=f.helper.getSettings(f.reference.service_id).tts.voices;
  assert.deepEqual(Object.keys(projected),['de']);
  assert.equal(projected.de.tts_config_sys_id,f.reference.tts_config_sys_id);
  assert.equal(JSON.stringify(projected.de.reference),JSON.stringify(f.reference));
  assert.equal(projected.de.reference.reference_language,'de');
  const stream=f.helper.getVoiceReferenceStream(f.reference.service_id,'de',f.reference);
  assert.equal(stream,f.streams[1]);
  assert.equal(f.streams.length,2);
  assert.throws(() => f.helper.getVoiceReferenceStream(f.reference.service_id,'en',f.reference),/unavailable/);
});

test('foreign service or attachment parent is rejected before any content stream opens', () => {
  for (const mutation of [f => {f.rows.sys_attachment[0].table_sys_id='d'.repeat(32);},
      f => {f.rows.sys_attachment[0].table_name='sys_user';},
      f => {f.rows.sn_voice_language_config[0].deployment='d'.repeat(32);}]) {
    const f=helperFixture(); mutation(f);
    // A missing selected native language row cannot authorize a different service descriptor.
    const service=f.rows.sn_voice_language_config[0].deployment!==f.reference.service_id ? 'd'.repeat(32) : f.reference.service_id;
    assert.throws(() => f.helper.getVoiceReferenceStream(service,'de',f.reference),/unavailable/);
    assert.equal(f.streams.length,0);
  }
});

test('row, field and schema refusal precede metadata value reads', () => {
  for (const options of [{deniedRow:'sys_attachment'},
      {deniedField:{table:'sys_attachment',field:'file_name'}},
      {invalidField:{table:'sys_attachment',field:'file_name'}}]) {
    const f=helperFixture(options);
    assert.throws(() => f.helper.getSettings(f.reference.service_id),/unavailable/);
    assert.equal(f.reads.filter(read => read.table==='sys_attachment').length,0);
    assert.equal(f.streams.length,0);
  }
});

test('digest mismatch or changed selection, metadata or actor prevents response reopening', () => {
  for (const options of [{digest:'0'.repeat(64)},
      {onDigest:({rows}) => { rows.sn_voice_tts_config[0].voice_id='changed-voice'; }},
      {onDigest:({rows}) => { rows.sys_attachment[0].sys_mod_count='2'; }},
      {onDigest:({setActor}) => setActor('e'.repeat(32))}]) {
    const f=helperFixture(options);
    assert.throws(() => f.helper.getVoiceReferenceStream(f.reference.service_id,'de',f.reference),/unavailable/);
    assert.equal(f.streams.length,1);
  }
});

test('descriptor contract rejects unknown keys, wrong types, limits and invalid consent dates', () => {
  const f=helperFixture();
  const check=value => f.helper._checkedReference(value,f.reference.service_id,f.reference.tts_config_sys_id,f.reference.voice_id);
  assert.equal(check(f.reference).provenance.confirmed_at_utc,f.reference.provenance.confirmed_at_utc);
  for (const mutation of [r => {r.extra=true;},r => {r.version='1';},r => {r.sha256=Array(64).fill('a');},
      r => {r.attachment_sys_id=Array(32).fill('a');},r => {r.size_bytes=44;},r => {r.size_bytes=6*1024*1024+1;},
      r => {r.reference_text='short\nline';},r => {r.reference_text='x'.repeat(1501);},
      r => {r.reference_language='../../de';},r => {r.provenance.confirmed_at_utc='2026-02-30T12:00:00.123456+00:00';},
      r => {r.provenance.confirmed_at_utc='2026-11-06T12:00:00+25:00';},r => {r.provenance.unapproved=true;}]) {
    const value=clone(f.reference);mutation(value);assert.throws(() => check(value),/unavailable/);
  }
  const row=f.rows.sn_voice_tts_config[0], parameters=JSON.parse(row.parameters);
  parameters.scc.engine='unrecognized';row.parameters=JSON.stringify(parameters);
  assert.throws(() => f.helper.getSettings(f.reference.service_id),/unavailable/);
});

function resourceFixture(payload,options={}) {
  const calls=[];const output={headers:{}};
  const request={body:{data:payload},getHeader:() => options.authorization===undefined ? 'Bearer opaque-original-caller' : options.authorization};
  const response={setStatus:value => {output.status=value;},setBody:value => {output.body=value;},
    setContentType:value => {output.contentType=value;},setHeader:(key,value) => {output.headers[key]=value;},
    getStreamWriter:() => ({writeStream:value => {output.stream=value;}})};
  const stream={raw:'WAV'};
  const context={request,response,gs:{getUserID:() => actor,getUserName:() => options.guest ? 'guest':'approved.caller'},
    VoiceRestUtils:function(){
      this.validateServiceId=() => {calls.push('service');return options.service!==false;};
      this.validateServiceAuthorization=() => {calls.push('nativeAuthorization');return options.nativeAuthorization!==false;};
      this.isTestMode=() => false;
    },
    VoiceAgentUtils:function(){this.getAuthorizedAgentIds=() => {calls.push('agents');return options.agents===undefined ? [agent]:options.agents;};},
    LocalLLMVoiceAssistantSettings:function(){
      this.getVoiceReferenceStream=(service,language,reference) => {calls.push('reference');assert.equal(service,descriptor.service_id);assert.equal(language,'de');assert.equal(reference,payload.reference);return stream;};
      this.getSettings=() => {calls.push('settings');return {version:1,service_id:descriptor.service_id};};
    }};
  vm.createContext(context);vm.runInContext(resourceSource,context,{filename:'Authorized-agents-resource.candidate.js'});
  return {calls,output,stream};
}

test('existing native authorization gates raw WAV opt-in while legacy JSON remains intact', () => {
  const payload={serviceId:descriptor.service_id,assistantSettingsVersion:1,voiceReferenceVersion:1,language:'de',reference:clone(descriptor)};
  const success=resourceFixture(payload);
  assert.deepEqual(success.calls,['service','nativeAuthorization','agents','reference']);
  assert.equal(success.output.status,200);assert.equal(success.output.contentType,'audio/wav');
  assert.equal(success.output.headers['Cache-Control'],'no-store');assert.equal(success.output.stream,success.stream);
  assert.equal(success.output.body,undefined);
  for (const options of [{service:false},{nativeAuthorization:false},{agents:[]},{authorization:''},{guest:true}]) {
    const denied=resourceFixture(payload,options);
    assert.equal(denied.calls.includes('reference'),false);assert.equal(denied.output.stream,undefined);
  }
  for (const bad of [{...payload,voiceReferenceVersion:2},{...payload,unexpected:true}]) {
    const denied=resourceFixture(bad);assert.equal(denied.output.status,403);assert.equal(denied.calls.includes('reference'),false);
  }
  const legacy=resourceFixture({serviceId:descriptor.service_id});
  assert.equal(legacy.output.status,200);assert.equal(JSON.stringify(legacy.output.body),JSON.stringify([agent]));
  assert.equal(legacy.calls.includes('reference'),false);assert.equal(legacy.output.stream,undefined);
  const settings=resourceFixture({serviceId:descriptor.service_id,assistantSettingsVersion:1});
  assert.equal(settings.output.status,200);assert.equal(settings.output.body.assistant_settings.version,1);
  assert.equal(settings.calls.includes('reference'),false);assert.equal(settings.output.stream,undefined);
});
