'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '..', 'VoiceServiceConfigurationMobile.js'), 'utf8');
const id = '8aa131d793f787105c8132d47aba1095';
const pin = 'https://strix-alloy.tail7f425a.ts.net/scc-native';
const prefix = 'sn_nowassist_va.scc_native_voice.';
function fixture({admin=true, properties={}, fallback='inherited', fail, logFail}={}) {
  const props = { [prefix+'enabled']:'true', [prefix+'assistant_id']:id,
    [prefix+'orchestrator_url']:pin, instance_name:'soprasteriaassvsdemo14', ...properties };
  const calls=[]; const diagnostics=[];
  function Parent() {}
  Parent.prototype = {
    initialize() {},
    _generateUrl(...args) { calls.push({self:this,args}); if(fail)throw fail; return fallback; },
    getMobileVoiceConfigurations() {return [id, '00000000000000000000000000000000'].map(voiceServiceId => ({voiceServiceId,voiceWebhookURL:this._generateUrl(voiceServiceId)}));}
  };
  const sandbox = {Class:{create:()=>function(){}},VoiceServiceConfigurationMobileSNC:Parent,
    gs:{hasRole:role => admin && role==='admin',getProperty:(key,otherwise)=>Object.hasOwn(props,key)?props[key]:otherwise,
      info:message=>{if(logFail)throw logFail;diagnostics.push(message);}}};
  vm.createContext(sandbox);
  vm.runInContext('Object.extendsObject = function(parent, values) { return Object.assign(Object.create(parent.prototype), values); };',sandbox);
  vm.runInContext(source,sandbox);
  return {instance:new sandbox.VoiceServiceConfigurationMobile(),calls,diagnostics};
}
test('mapped SCC admin configuration uses the exact native HTTPS endpoint',()=>{
  const {instance,calls}=fixture();
  assert.equal(instance._generateUrl(id),pin+'/webrtc/connect/agent_operator?instance_name=soprasteriaassvsdemo14&voice_service_id='+id);
  assert.equal(calls.length,0);
});
test('inherited configuration enumeration dispatches through the override',()=>{
  const {instance,calls}=fixture();const rows=instance.getMobileVoiceConfigurations();
  assert.ok(rows[0].voiceWebhookURL.startsWith(pin+'/')); assert.equal(rows[1].voiceWebhookURL,'inherited');
  assert.equal(calls.length,1);
});
test('both native query values are URL encoded and contain no token',()=>{
  const {instance}=fixture({properties:{instance_name:'demo lab&auth_token=evil/#ü'}});
  const url=instance._generateUrl(id); const parsed=new URL(url);
  assert.equal(parsed.searchParams.get('instance_name'),'demo lab&auth_token=evil/#ü');
  assert.equal(parsed.searchParams.get('voice_service_id'),id);
  assert.equal(parsed.searchParams.has('auth_token'),false); assert.equal(parsed.hash,'');
});
test('one trailing slash on the approved endpoint is normalized',()=>{
  const {instance}=fixture({properties:{[prefix+'orchestrator_url']:pin+'/'}});
  assert.ok(instance._generateUrl(id).startsWith(pin+'/webrtc/'));
});
test('role, flag, assistant and endpoint guard failures retain SNC routing',()=>{
  const cases=[{admin:false},{properties:{[prefix+'enabled']:'false'}},{properties:{[prefix+'enabled']:true}},
    {properties:{[prefix+'assistant_id']:''}},{properties:{[prefix+'assistant_id']:'00000000000000000000000000000000'}},
    {properties:{[prefix+'orchestrator_url']:''}},{properties:{[prefix+'orchestrator_url']:pin+'//'}},
    {properties:{[prefix+'orchestrator_url']:pin+'?x=1'}},{properties:{[prefix+'orchestrator_url']:'https://unapproved.example/scc-native'}}];
  for(const options of cases){const {instance,calls}=fixture(options);assert.equal(instance._generateUrl(id),'inherited');assert.equal(calls.length,1);}
});
test('other, empty and missing service IDs preserve fallback arguments and receiver',()=>{
  for(const service of ['00000000000000000000000000000000','',null,undefined]){
    const {instance,calls}=fixture();assert.equal(instance._generateUrl(service,'extra'),'inherited');
    assert.equal(calls[0].self,instance);assert.deepEqual(calls[0].args,[service,'extra']);
  }
});
test('inherited null, dash, objects and thrown errors remain unchanged',()=>{
  for(const value of [null,'-',false,{legacy:true}]){
    const {instance}=fixture({admin:false,fallback:value});assert.equal(instance._generateUrl(id),value);
  }
  const error=new Error('legacy failure');const {instance}=fixture({admin:false,fail:error});
  assert.throws(()=>instance._generateUrl(id),e=>e===error);
});

function readDiagnostic(records) {
  assert.equal(records.length,1);
  const prefix='[SCC Mobile Voice Route] ';
  assert.ok(records[0].startsWith(prefix));
  return JSON.parse(records[0].slice(prefix.length));
}
test('route diagnostics identify the local SCC path with only bounded booleans',()=>{
  const {instance,diagnostics}=fixture();
  instance._generateUrl(id);
  assert.deepEqual(readDiagnostic(diagnostics),{route:'local',approved_service:true,admin:true,enabled:true,endpoint_matches:true});
});
test('fallback diagnostics disclose no input, instance, URI or credential values',()=>{
  const secret='Bearer user-token-canary';
  const {instance,diagnostics}=fixture({admin:false,properties:{
    instance_name:secret,[prefix+'orchestrator_url']:'https://'+secret+'/private',
    [prefix+'assistant_id']:secret,[prefix+'enabled']:'false'}});
  assert.equal(instance._generateUrl(secret),'inherited');
  assert.deepEqual(readDiagnostic(diagnostics),{route:'snc',approved_service:false,admin:false,enabled:false,endpoint_matches:false});
  assert.ok(!diagnostics[0].includes(secret));
  assert.ok(!diagnostics[0].includes('https://'));
  assert.ok(!diagnostics[0].includes(id));
});
test('a logging failure cannot change either local or inherited endpoint behavior',()=>{
  for(const admin of [true,false]){
    const {instance}=fixture({admin,logFail:new Error('log unavailable')});
    const value=instance._generateUrl(id);
    assert.equal(value,admin?pin+'/webrtc/connect/agent_operator?instance_name=soprasteriaassvsdemo14&voice_service_id='+id:'inherited');
  }
});
