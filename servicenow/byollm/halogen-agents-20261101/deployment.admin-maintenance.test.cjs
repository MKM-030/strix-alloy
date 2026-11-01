'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const crypto=require('node:crypto');
const privateDirectory=path.resolve(__dirname,'../../../server/.local/voice-goal-halogen-agents-20261101');
const originalHash='b14dd89fcc6114cdf311c6c6f09795d7ea2b3c93f9fc49414258e8fbc413b649';
const sha=s=>crypto.createHash('sha256').update(s).digest('hex');
const clone=x=>JSON.parse(JSON.stringify(x));
const originalPlan=JSON.parse(fs.readFileSync(path.join(privateDirectory,'frozen-plan.private.json'),'utf8'));
function maintenancePlan(){return {...clone(originalPlan),authorityMode:'approved_admin_maintenance',marker:originalPlan.marker+'_ADMIN_TEST'};}
// A narrow native-boundary double: Secure reads are enforced; ordinary records
// cannot query or inspect values and may load/update only the frozen source IDs.
function platform(plan,options={}){
  const db={sys_update_set:[],sys_update_xml:[],sys_es_latest_script:[]},writes=[],ordinaryLoads=[],secureSourceReads=new Set();let seq=5000,selected='original-set',receipt,updateAttempts=0;
  const targets=new Map(plan.targets.map(t=>[t.table+':'+t.id,t]));
  const booleanField=(table,f)=>['active','default','is_default','use_es_latest'].includes(f);
  for(const item of [...plan.targets,...plan.guards]){db[item.table]??=[];if(!db[item.table].some(r=>r.sys_id===item.id))db[item.table].push({...clone(item.before),...(targets.has(item.table+':'+item.id)?{sys_policy:''}:{}),unqueried_contract:'preserved'});}
  const enc=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
  const dec=s=>s.replaceAll('&lt;','<').replaceAll('&gt;','>').replaceAll('&amp;','&');
  class Record{
    constructor(table,secure=false){this.table=table;this.secure=secure;this.filters=[];this.limit=Infinity;if(!secure)assert.ok(plan.targets.some(t=>t.table===table),'ordinary record table outside frozen source set');}
    isValid(){return !!db[this.table];}
    get(key){this.row=db[this.table]?.find(r=>r.sys_id===key);if(!this.secure){assert.ok(targets.has(this.table+':'+key),'ordinary record identity outside frozen source set');assert.equal(secureSourceReads.size,68,'all source Secure preflights precede ordinary load');ordinaryLoads.push(key);}else if(targets.has(this.table+':'+key))secureSourceReads.add(key);return !!this.row;}
    getUniqueValue(){return this.row.sys_id;} getRecordClassName(){return this.table;}
    canRead(){assert.ok(this.secure);return this.row.sys_id!==options.denyRead;}
    canWrite(){assert.ok(this.secure);return options.uiWritable===true;}
    isValidField(f){assert.ok(this.secure);return Object.hasOwn(this.row,f);}
    getValue(f){assert.ok(this.secure,'ordinary values must never be inspected');const value=this.row[f]??'';return options.nativeBooleans&&booleanField(this.table,f)?value==='true'?'1':value==='false'?'0':value:value;}
    getElement(f){assert.ok(this.secure);return {getName:()=>f,canRead:()=>!(options.denyField&&this.row.sys_id===options.denyField.id&&f===options.denyField.field),canWrite:()=>options.uiWritable===true,getED:()=>({getInternalType:()=>booleanField(this.table,f)?'boolean':'string'})};}
    getElements(){assert.ok(this.secure);const fields=Object.keys(this.row).map(f=>this.getElement(f));return {size:()=>fields.length,get:i=>fields[i]};}
    addQuery(f,op,v){assert.ok(this.secure,'ordinary queries prohibited');this.filters.push([f,v===undefined?'=':op,v===undefined?op:v]);}
    setLimit(n){this.limit=n;} query(){assert.ok(this.secure);this.results=(db[this.table]||[]).filter(r=>this.filters.every(([f,op,v])=>op==='IN'?String(v).split(',').includes(r[f]??''):(r[f]??'')===String(v))).slice(0,this.limit);this.cursor=0;}
    next(){this.row=this.results[this.cursor++];return !!this.row;}
    initialize(){assert.ok(this.secure);assert.equal(this.table,'sys_update_set');this.row={};}
    setValue(f,v){if(!this.secure){const t=targets.get(this.table+':'+this.row.sys_id);assert.equal(f,t.field,'ordinary assignment outside frozen field');assert.equal(v,t.desired,'ordinary assignment outside frozen desired value');}this.row[f]=String(v);}
    insert(){assert.ok(this.secure);assert.equal(this.table,'sys_update_set');this.row.sys_id=(++seq).toString(16).padStart(32,'0');this.row.batch_base=this.row.parent||'';db[this.table].push(this.row);writes.push({table:this.table,id:this.row.sys_id,kind:'insert'});return this.row.sys_id;}
    update(){
      assert.equal(this.secure,false,'maintenance source writes require bounded ordinary record');updateAttempts++;
      if(options.nativePolicyReject)throw Error('native_policy_rejected');
      this.row.sys_mod_count=String(Number(this.row.sys_mod_count||0)+1);this.row.sys_updated_on='2026-11-01 18:00:00';this.row.sys_updated_by='approved-admin';if(this.table==='sys_generative_ai_config')this.row.request_tokens='8192';
      writes.push({table:this.table,id:this.row.sys_id,kind:'update'});return this.row.sys_id;
    }
  }
  class Secure extends Record{constructor(table){super(table,true);}}
  class UpdateSet{set(value){selected=value;}}
  class Manager{
    constructor(){assert.equal(arguments.length,0);}
    saveRecord(gr){
      assert.ok(gr.secure,'capture must use Secure source read');const name=gr.row.sys_update_name||gr.table+'_'+gr.row.sys_id;
      const serialize=(table,row)=>'<'+table+' action="INSERT_OR_UPDATE">'+Object.entries(row).map(([k,v])=>'<'+k+'>'+enc(v)+'</'+k+'>').join('')+'</'+table+'>';
      let body=serialize(gr.table,gr.row);for(const c of plan.companions)if(c.owner===gr.row.sys_id)body+=serialize(c.table,db[c.table].find(r=>r.sys_id===c.id));
      const u={sys_id:(++seq).toString(16).padStart(32,'0'),name,update_set:selected,application:gr.row.sys_scope,action:'INSERT_OR_UPDATE',payload:'<record_update table="'+gr.table+'">'+body+'</record_update>'};db.sys_update_xml.push(u);writes.push({table:'sys_update_xml',id:u.sys_id,kind:'capture'});
    }
  }
  class XML{
    parseXML(text){this.xml=text;return true;}
    getDocumentElement(){const m=this.xml.match(/^<record_update table="([^"]+)">/);return m?{getAttribute:k=>k==='table'?m[1]:''}:null;}
    getNodeText(xpath){const parts=xpath.split('/').filter(Boolean),field=parts.at(-1),table=parts.at(-2),record=this.xml.match(new RegExp('<'+table+'(?:\\s[^>]*?)?>([\\s\\S]*?)</'+table+'>'));const m=record?.[1].match(new RegExp('<'+field+'>([\\s\\S]*?)</'+field+'>'));return m?dec(m[1]):'';}
  }
  const context={GlideRecordSecure:Secure,GlideRecord:Record,GlideUpdateSet:UpdateSet,GlideUpdateManager2:Manager,XMLDocument2:XML,gs:{hasRole:r=>r==='admin'&&options.admin!==false,getPreference:()=>selected,info:message=>{receipt=JSON.parse(message.slice(message.indexOf('{')));}}};
  function run(useOriginal=false){const p=path.join(__dirname,useOriginal?'apply-halogen-agent-configuration.template.js':'apply-halogen-agent-configuration.admin-maintenance.template.js');const source=fs.existsSync(p)?fs.readFileSync(p,'utf8'):'';receipt=null;vm.runInNewContext(source.replace('/*__FROZEN_PLAN__*/',JSON.stringify(plan)),context);return receipt;}
  return {db,writes,ordinaryLoads,run,get selected(){return selected;},get updateAttempts(){return updateAttempts;}};
}
test('original Secure mode still rejects a UI write-restricted target without any writes',()=>{
  const p=platform(clone(originalPlan));const r=p.run(true);assert.equal(r.ok,false);assert.match(r.error,/target_write_denied/);assert.equal(p.writes.length,0);assert.equal(p.ordinaryLoads.length,0);
});
test('maintenance mode missing explicit authority aborts before any write or ordinary load',()=>{
  const p=platform(clone(originalPlan)),r=p.run();assert.ok(r,'maintenance variant must emit receipt');assert.equal(r.ok,false);assert.match(r.error,/authority|maintenance_mode/);assert.equal(p.writes.length,0);assert.equal(p.ordinaryLoads.length,0);
});
test('maintenance authority without admin role aborts before any write',()=>{
  const p=platform(maintenancePlan(),{admin:false}),r=p.run();assert.ok(r);assert.equal(r.ok,false);assert.match(r.error,/admin_required/);assert.equal(p.writes.length,0);assert.equal(p.ordinaryLoads.length,0);
});
test('explicit approved admin maintenance updates only68 frozen fields despite UI denial and captures via Secure reads',()=>{
  const plan=maintenancePlan(),p=platform(plan),before=clone(p.db),r=p.run();assert.ok(r,'maintenance variant must emit receipt');assert.equal(r.ok,true,r.error);assert.equal(r.authority_mode,'approved_admin_maintenance');assert.equal(r.ui_write_restricted_count,68);assert.equal(r.ui_write_restricted_ids.length,68);assert.equal(r.source_writes,68);assert.equal(r.captured,68);assert.equal(p.ordinaryLoads.length,68);assert.equal(p.selected,'original-set');
  const expectedTables=new Set([...plan.targets.map(t=>t.table),'sys_update_set','sys_update_xml']);for(const w of p.writes)assert.ok(expectedTables.has(w.table));
  for(const t of plan.targets){const row=p.db[t.table].find(x=>x.sys_id===t.id),old=before[t.table].find(x=>x.sys_id===t.id);for(const [k,v] of Object.entries(old))if(k!==t.field&&!['sys_updated_on','sys_mod_count'].includes(k))assert.equal(row[k],v,'unintended change '+k);assert.equal(row[t.field],t.desired);}
  for(const g of plan.guards)assert.deepEqual(p.db[g.table].find(x=>x.sys_id===g.id),before[g.table].find(x=>x.sys_id===g.id));
  const count=p.writes.length,loads=p.ordinaryLoads.length,again=p.run();assert.equal(again.ok,true,again.error);assert.equal(again.status,'already_applied');assert.equal(p.writes.length,count);assert.equal(p.ordinaryLoads.length,loads);
});
test('native dictionary booleans 1/0 match SDK true/false snapshots and native XML while string values stay unchanged',()=>{
  const plan=maintenancePlan(),p=platform(plan,{nativeBooleans:true}),r=p.run();assert.equal(r.ok,true,r.error);assert.equal(r.source_writes,68);assert.equal(r.captured,68);assert.equal(p.selected,'original-set');
  for(const row of p.db.sys_properties)assert.equal(row.value,'false','Mirror value is a string, not a dictionary boolean');
  for(const row of p.db.sys_es_latest_script){assert.equal(row.use_es_latest,'true');assert.equal(row.sys_mod_count,'0','string revision zero must not become false');}
  for(const row of p.db.sys_update_xml)assert.doesNotMatch(row.payload,/<(?:active|default|use_es_latest)>[01]</);
  const count=p.writes.length;assert.equal(p.run().status,'already_applied');assert.equal(p.writes.length,count);
});
test('an invalid dictionary boolean rejects before all writes rather than guessing',()=>{
  const first=originalPlan.targets[0],p=platform(maintenancePlan(),{nativeBooleans:true});p.db[first.table].find(r=>r.sys_id===first.id).active='invalid';
  const r=p.run();assert.equal(r.ok,false);assert.match(r.error,/invalid_boolean/);assert.equal(p.writes.length,0);assert.equal(p.ordinaryLoads.length,0);
});
test('record read denial remains enforced and prevents ordinary source access',()=>{
  const p=platform(maintenancePlan(),{denyRead:originalPlan.targets[0].id}),r=p.run();assert.ok(r);assert.equal(r.ok,false);assert.match(r.error,/record_unavailable/);assert.equal(p.writes.length,0);assert.equal(p.ordinaryLoads.length,0);
});
test('unreadable frozen field remains a precondition failure before writes',()=>{
  const p=platform(maintenancePlan(),{denyField:{id:originalPlan.targets[0].id,field:'prompt'}}),r=p.run();assert.ok(r);assert.equal(r.ok,false);assert.match(r.error,/preimage_drift/);assert.equal(p.writes.length,0);assert.equal(p.ordinaryLoads.length,0);
});
test('nonempty protection policy on the last frozen source aborts before every database write',()=>{
  const last=originalPlan.targets.at(-1),p=platform(maintenancePlan());p.db[last.table].find(r=>r.sys_id===last.id).sys_policy='read';
  const r=p.run();assert.equal(r.ok,false);assert.match(r.error,/source_policy_protected/);assert.equal(p.writes.length,0);assert.equal(p.ordinaryLoads.length,0);
});
test('unreadable protection policy aborts before every database write',()=>{
  const p=platform(maintenancePlan(),{denyField:{id:originalPlan.targets.at(-1).id,field:'sys_policy'}}),r=p.run();assert.equal(r.ok,false);assert.match(r.error,/field_unavailable:sys_policy/);assert.equal(p.writes.length,0);assert.equal(p.ordinaryLoads.length,0);
});
test('a native update rejection stops once, preserves the failure and restores context',()=>{
  const p=platform(maintenancePlan(),{nativePolicyReject:true}),r=p.run();assert.ok(r);assert.equal(r.ok,false);assert.equal(r.status,'partial_or_uncertain');assert.match(r.error,/native_policy_rejected/);assert.equal(p.updateAttempts,1);assert.equal(r.source_writes,0);assert.equal(r.captured,0);assert.equal(p.selected,'original-set');
});
test('separate builder binds to the original approved artifact without overwriting it',()=>{
  const p=path.join(__dirname,'build-admin-maintenance.cjs'),builder=fs.existsSync(p)?require(p):{prepare:()=>null};
  const before=fs.readFileSync(path.join(privateDirectory,'apply-halogen-agent-configuration.js'));assert.equal(sha(before),originalHash);
  const prepared=builder.prepare(privateDirectory);assert.ok(prepared,'additional variant builder must prepare reviewable output');assert.equal(prepared.plan.authorityMode,'approved_admin_maintenance');assert.equal(prepared.plan.targets.length,68);assert.deepEqual(prepared.plan.targets,originalPlan.targets);assert.deepEqual(prepared.plan.guards,originalPlan.guards);assert.deepEqual(prepared.plan.companions,originalPlan.companions);assert.equal(sha(fs.readFileSync(path.join(privateDirectory,'apply-halogen-agent-configuration.js'))),originalHash);new Function(prepared.script);
});
