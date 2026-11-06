'use strict';
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const test = require('node:test'), assert = require('node:assert/strict'), crypto = require('node:crypto');
const DIR = __dirname;
const SOURCES = {SCCVoiceContextReadPolicy:'SCCVoiceContextReadPolicy.js', SCCVoiceCallerContext:'SCCVoiceCallerContext.v1.candidate.js'};
const ID = {actor:'6a0690b893d00b105c8132d47aba1022', c:'11111111111111111111111111111111', i:'22222222222222222222222222222222', p:'33333333333333333333333333333333', n:'44444444444444444444444444444444', req:'55555555555555555555555555555555', other:'66666666666666666666666666666666', profile:'c623e20f93374354e7f2b9fa6aba1081', workflow:'2f3c8a39931093185c8132d47aba1014', provider:'200af60f93fb4354e7f2b9fa6aba107d'};
const REFS = new Set(['interaction.provider_application','sys_cs_conversation.context_profile','sn_aia_execution_plan.usecase']);
const PROMPT = '<inputs><scratchpad>[]</scratchpad><memory><conversation_history>{}</conversation_history></memory></inputs>';
function source(name) { return fs.readFileSync(path.join(DIR, SOURCES[name]),'utf8'); }
function fixture(options={}) {
  const accesses=[], queries=[], counters={depth:0,maxDepth:0}, db={
    sys_cs_conversation:[{sys_id:ID.c,context_profile:ID.profile,state:'open'}],
    interaction:[{sys_id:ID.i,opened_for:ID.actor,provider_application:ID.provider,channel_metadata_table:'sys_cs_conversation',channel_metadata_document:ID.c}],
    sn_aia_execution_plan:[{sys_id:ID.p,conversation:ID.c,state:'in_progress',usecase:ID.workflow}], sn_aia_message:[]
  };
  let context, policy, messageQueryCount=0, actor=ID.actor;
  function Record(table, raw=false, row=null) { this.table=table;this.raw=raw;this.row=row;this.conditions=[];this.limit=Infinity;this.rows=[];this.index=-1; }
  Record.prototype.isValid=function(){return Object.hasOwn(db,this.table);};
  Record.prototype.getTableName=function(){return this.table;};
  Record.prototype.isValidField=function(field){return !(options.missingFields||[]).includes(this.table+'.'+field) && (this.raw || options.maskedRefs===false || !REFS.has(this.table+'.'+field)) && Object.hasOwn(this.row||db[this.table][0]||{},field);};
  Record.prototype.getUniqueValue=function(){return this.row && this.row.sys_id;};
  Record.prototype.getValue=function(field){
    if (!this.raw && REFS.has(this.table+'.'+field)) { accesses.push('getValue:'+this.table+'.'+field); if(options.maskedRefs!==false)throw Error('Protected projected reference read'); }
    if((options.deniedFields||[]).includes(this.table+'.'+field))throw Error('Denied field read');
    return this.row && this.row[field];
  };
  Record.prototype.getElement=function(field){
    if(!this.raw && REFS.has(this.table+'.'+field)){accesses.push('getElement:'+this.table+'.'+field);if(options.maskedRefs!==false)return null;}
    if((options.missingFields||[]).includes(this.table+'.'+field) || !Object.hasOwn(this.row||{},field))return null;
    return {canRead:()=>!(options.deniedFields||[]).includes(this.table+'.'+field)};
  };
  Record.prototype.addQuery=function(field,operator,value){ if(arguments.length===2){value=operator;operator='=';}this.conditions.push([field,operator,value]);return {}; };
  Record.prototype.setLimit=function(n){this.limit=n;};
  Record.prototype.query=function(){
    queries.push({table:this.table,conditions:this.conditions.map(x=>x.slice())});
    if(this.table==='sn_aia_message' && ++messageQueryCount===1 && options.onMessageQuery)options.onMessageQuery(db,()=>{actor=ID.other;});
    this.rows=db[this.table].filter(row=>this.conditions.every(([field,op,value])=>{
      if((options.ignoredFilters||[]).includes(this.table+'.'+field))return true;
      if(op==='STARTSWITH')return String(row[field]||'').startsWith(value);
      assert.equal(op,'=');return String(row[field]??'')===String(value);
    })).slice(0,this.limit);this.index=-1;
  };
  Record.prototype.canRead=function(){
    if(!this.row || (options.deniedRows||[]).includes(this.table))return false;
    if(this.raw || options.nativeOtherAllow)return true;
    if(++counters.depth>18)throw Error('ACL recursion');counters.maxDepth=Math.max(counters.maxDepth,counters.depth);
    try{return policy.canRead(this.table,new Record(this.table,true,this.row))===true;}finally{counters.depth--;}
  };
  Record.prototype.next=function(){while(++this.index<this.rows.length){this.row=this.rows[this.index];if(this.canRead())return true;}this.row=null;return false;};
  Record.prototype.get=function(id){this.addQuery('sys_id',id);this.query();return this.next();};
  context=vm.createContext({Class:{create:()=>function(){if(this.initialize)this.initialize();}},
    GlideRecordSecure:function(table){return new Record(table);},
    gs:{getUserID:()=>actor,hasRole:()=>options.readerRole!==false,info(){},warn(){},error(){}},
    GlideDigest:function(){this.getSHA256Hex=text=>crypto.createHash('sha256').update(text).digest('hex');},
    sn_aia:{AIAgentConstants:{ROLES:{USER:'user'}},AgentCommunicationUtil:function(){this.addMessageToShortTermMemory=(pid,role,message,user_message)=>{if(options.ackWriteFailure)throw Error('Uncertain receipt');db.sn_aia_message.push({sys_id:'77777777777777777777777777777777',execution_plan:pid,role,message,user_message});};}},
    global:{SCCVoicePresentationHistoryV1:function(){this.includeJSON=()=>JSON.stringify({historyIncluded:false,prompt:null,historyEventIds:[]});}}
  });
  vm.runInContext(source('SCCVoiceContextReadPolicy'),context);policy=new context.SCCVoiceContextReadPolicy();
  vm.runInContext(source('SCCVoiceCallerContext'),context);const helper=new context.SCCVoiceCallerContext();
  const text='Beginn 16. November, Standort Hamburg.\nKorrektur: Standort Berlin.';
  const message=helper.noteText(ID.req,1,text);db.sn_aia_message.push({sys_id:ID.n,execution_plan:ID.p,role:'user',message,user_message:message});
  if(options.mutate)options.mutate(db);
  return {db,helper,policy,queries,accesses,counters,text,message,raw:(table,index=0)=>new Record(table,true,db[table][index]),run:()=>JSON.parse(helper.includeJSON(JSON.stringify({request_data:{_meta:{conversationId:ID.c}},prompt:PROMPT})))};
}
test('masked configured references retain own note inclusion and exact technical receipt',()=>{
  const f=fixture(),r=f.run();assert.equal(r.promptIncluded,true);assert.equal(r.receiptStored,true);assert.equal(r.contextRequestId,ID.req);assert.equal(r.revision,1);assert.equal(r.executionPlanId,ID.p);
  assert.ok(r.prompt.includes(f.helper.promptProvenance+'\n'+f.text));assert.ok(r.prompt.indexOf(f.text)<r.prompt.indexOf('</memory>'));
  assert.equal(f.db.sn_aia_message.length,2);assert.equal(f.db.sn_aia_message[1].message,f.helper.ackText(f.helper.parseNote(f.message)));assert.deepEqual(f.accesses,[]);assert.ok(f.counters.maxDepth<10);
});
test('policy raw current-row scopes survive masked secure projections',()=>{const f=fixture();assert.equal(f.policy.canRead('sys_cs_conversation',f.raw('sys_cs_conversation')),true);assert.equal(f.policy.canRead('sn_aia_execution_plan',f.raw('sn_aia_execution_plan')),true);assert.equal(f.policy.canRead('sn_aia_message',f.raw('sn_aia_message')),true);});
for(const [label,mutate] of [
 ['cross owner',d=>d.interaction[0].opened_for=ID.other],['wrong provider',d=>d.interaction[0].provider_application=ID.other],
 ['wrong profile',d=>d.sys_cs_conversation[0].context_profile=ID.other],['wrong workflow',d=>d.sn_aia_execution_plan[0].usecase=ID.other],
 ['closed conversation',d=>d.sys_cs_conversation[0].state='completed'],['closed plan',d=>d.sn_aia_execution_plan[0].state='completed'],
 ['wrong interaction table',d=>d.interaction[0].channel_metadata_table='incident'],['wrong interaction join',d=>d.interaction[0].channel_metadata_document=ID.other],
 ['ambiguous interaction',d=>d.interaction.push({...d.interaction[0],sys_id:ID.other})],['ambiguous live plan',d=>d.sn_aia_execution_plan.push({...d.sn_aia_execution_plan[0],sys_id:ID.other})],
 ['note dual text conflict',d=>d.sn_aia_message[0].user_message+=' changed']
]) test('helper rejects '+label+' even when other native read ACLs allow rows',()=>{const f=fixture({mutate,nativeOtherAllow:true});const r=f.run();assert.equal(r.promptIncluded,false);assert.equal(r.prompt,PROMPT);assert.equal(f.db.sn_aia_message.length,1);});
for(const field of REFS)test('ignored '+field+' predicate is detected by same-owned-ID negative control',()=>{const f=fixture({ignoredFilters:[field],nativeOtherAllow:true});const r=f.run();assert.equal(r.promptIncluded,false);assert.equal(r.prompt,PROMPT);assert.equal(f.db.sn_aia_message.length,1);});
for(const table of ['sys_cs_conversation','interaction','sn_aia_execution_plan','sn_aia_message'])test('denied '+table+' rows cannot include notes',()=>{const f=fixture({deniedRows:[table]});assert.equal(f.run().promptIncluded,false);assert.equal(f.db.sn_aia_message.length,1);});
for(const field of ['sys_cs_conversation.sys_id','sys_cs_conversation.state','interaction.sys_id','interaction.opened_for','interaction.channel_metadata_table','interaction.channel_metadata_document','sn_aia_execution_plan.sys_id','sn_aia_execution_plan.conversation','sn_aia_execution_plan.state','sn_aia_message.message'])test('denied ordinary field '+field+' refuses',()=>{const f=fixture({deniedFields:[field]});assert.equal(f.run().promptIncluded,false);assert.equal(f.db.sn_aia_message.length,1);});
for(const [label,mutation] of [['conversation closes',d=>d.sys_cs_conversation[0].state='completed'],['plan changes workflow',d=>d.sn_aia_execution_plan[0].usecase=ID.other],['ownership transfers',d=>d.interaction[0].opened_for=ID.other],['actor changes',(d,changeActor)=>changeActor()]])test('binding drift '+label+' is refused before receipt',()=>{const f=fixture({onMessageQuery:mutation,nativeOtherAllow:true});assert.equal(f.run().promptIncluded,false);assert.equal(f.db.sn_aia_message.length,1);});
test('technical acknowledgement uncertainty leaves real included note intact',()=>{const f=fixture({ackWriteFailure:true}),r=f.run();assert.equal(r.promptIncluded,true);assert.equal(r.receiptStored,false);assert.ok(r.prompt.includes(f.text));});
for(const [label,mutate] of [['wrong profile',d=>d.sys_cs_conversation[0].context_profile=ID.other],['wrong usecase',d=>d.sn_aia_execution_plan[0].usecase=ID.other],['wrong owner',d=>d.interaction[0].opened_for=ID.other]])test('current-row policy rejects '+label,()=>{const f=fixture({mutate});assert.equal(f.policy.canRead('sn_aia_message',f.raw('sn_aia_message')),false);});
test('reader role remains required by owned policy',()=>{const f=fixture({readerRole:false});assert.equal(f.policy.canRead('sn_aia_message',f.raw('sn_aia_message')),false);});
for(const field of ['sys_cs_conversation.sys_id','sys_cs_conversation.state','interaction.sys_id','interaction.opened_for','interaction.channel_metadata_table','interaction.channel_metadata_document','sn_aia_execution_plan.sys_id','sn_aia_execution_plan.conversation','sn_aia_execution_plan.state','sn_aia_message.message'])test('missing ordinary field '+field+' refuses',()=>{const f=fixture({missingFields:[field]});assert.equal(f.run().promptIncluded,false);assert.equal(f.db.sn_aia_message.length,1);});
for(const field of REFS)test('missing raw ACL predicate '+field+' refuses instead of replacing it with query inference',()=>{const f=fixture({missingFields:[field]});assert.equal(f.run().promptIncluded,false);assert.equal(f.db.sn_aia_message.length,1);});
test('repeated prompt inclusion does not duplicate technical receipt',()=>{const f=fixture();assert.equal(f.run().receiptStored,true);assert.equal(f.run().receiptStored,true);assert.equal(f.db.sn_aia_message.length,2);});
test('absence of supplemental notes retains native prompt and stores no receipt',()=>{const f=fixture();f.db.sn_aia_message=[];const r=f.run();assert.equal(r.promptIncluded,false);assert.equal(r.code,'context_note_absent');assert.equal(r.prompt,PROMPT);assert.equal(f.db.sn_aia_message.length,0);});
test('successful reader never opens protected configuration tables',()=>{const f=fixture();assert.equal(f.run().promptIncluded,true);assert.deepEqual([...new Set(f.queries.map(q=>q.table))].sort(),['interaction','sn_aia_execution_plan','sn_aia_message','sys_cs_conversation']);});
// Frozen from the deployed pre-repair policy revision 2 and caller revision 6.
// Normalize source line endings only; no private captures are needed to run.
test('interaction raw provider leaf and note parser/provenance/receipt protocol stay unchanged',()=>{
  const after=fixture(),sha=value=>crypto.createHash('sha256').update(value).digest('hex');
  const methods={
  "_ownInteraction": "ce3defef4b7eafec39294c48ad97379481d141428036361ee75c43ee13e29f85",
  "noteText": "f3b0808e74a49cf8de6fe00d257e6304a0b2a032cc4b10ca984b44e074f040cf",
  "parseNote": "23d01b8631341d2a4d97620a07afec268690c84e6c3d65228da179a941ae3b18",
  "orderedNotes": "5f331495dd71f53c87a5545fd29075fe798721c4dfe03974fe79b2e8a70d0e37",
  "ackText": "06c66b93a9c6baab2bab826f7908dda9d75d4f41390a9beb610868bfa30a6edb",
  "_exactAck": "e7f540736a6891749fbb3b63baeb94f9e9257f8a426278fb63ccdd8abb69546d"
};
  const constants={
  "notePrefix": "eec1cfc37a2f4d48649cc934852c0aa49b2c6a4ec18bd801d911524b5f8863ae",
  "provenance": "8c746dcafa57a06a93cba2fe7cb3741d9ad52eef972775100846e8715d0a9f6b",
  "receiptProvenance": "08eb0f33c331660a12c41b842001b1b120047b227a2e2c26119c33da9ee73b72",
  "promptProvenance": "2201d6c864a436815ca20d71158ee3a99baee56d937f182978bbb473ed1aeb46"
};
  for(const [key,expected] of Object.entries(methods)) {
    const actual=key==='_ownInteraction'?after.policy[key]:after.helper[key];
    assert.equal(sha(String(actual).replace(/\r\n/g,'\n')),expected,key);
  }
  for(const [key,expected] of Object.entries(constants))assert.equal(sha(after.helper[key]),expected,key);
});
