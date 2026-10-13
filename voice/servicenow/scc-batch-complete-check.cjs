// Local-only completion checks; no ServiceNow or network access.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const script=fs.readFileSync(path.join(__dirname,'scc-batch-complete.js'),'utf8');
const ROOT='194a7413933f0754e7f2b9fa6aba1080';
const children={'32808450431302106c3603295bb8f245':'514a7413933f0754e7f2b9fa6aba109c','7cc4ec81533121106b38ddeeff7b12ee':'d54a7413933f0754e7f2b9fa6aba109e',global:'114a7413933f0754e7f2b9fa6aba10a0'};
const name='SCC 2026 - Local Voice + ITSM Laptop Demo - 2026-10-12',marker='SCC_CAPTURE_MANIFEST_V1_2026_10_12';
function run(options={}){
 const db={sys_update_set:[{sys_id:ROOT,name,application:'global',parent:'',state:'in progress',description:marker}],sys_update_xml:[]};
 const frozen=[],xmlIds=[];let seq=1,writes=0,output;
 for(const [scope,id] of Object.entries(children)){
  db.sys_update_set.push({sys_id:id,name:name+' / '+scope,application:scope,parent:ROOT,batch_base:ROOT,state:'in progress',description:marker});
  const table='test_config_'+seq,recordId=String(seq).padStart(32,'0'),xmlId=String(seq+10).padStart(32,'0');
  db[table]=[{sys_id:recordId,sys_scope:scope,sys_updated_on:'2026-10-13 07:00:00',sys_mod_count:'1'}];
  frozen.push([table,recordId,scope,'2026-10-13 07:00:00','1']);xmlIds.push(xmlId);
  db.sys_update_xml.push({sys_id:xmlId,update_set:id,name:table+'_'+recordId,application:scope,action:'INSERT_OR_UPDATE',payload:`<record_update><${table}><sys_id>${recordId}</sys_id><sys_updated_on>2026-10-13 07:00:00</sys_updated_on><sys_mod_count>1</sys_mod_count></${table}></record_update>`});seq++;
 }
 if(options.staleSource)db.test_config_1[0].sys_mod_count='2';
 if(options.staleXml)db.sys_update_xml[0].payload=db.sys_update_xml[0].payload.replace('<sys_mod_count>1</sys_mod_count>','<sys_mod_count>0</sys_mod_count>');
 if(options.wrongXmlScope)db.sys_update_xml[0].application='global';
 if(options.wrongChild)db.sys_update_set[1].application='global';
 if(options.extraXml)db.sys_update_xml.push({sys_id:'unexpected',update_set:children.global,name:'extra',payload:''});
 if(options.extraChild)db.sys_update_set.push({sys_id:'unexpected',parent:ROOT});
 if(options.alreadyComplete)db.sys_update_set.forEach(r=>r.state='complete');
 const capture={ok:true,batch:ROOT,children,captured:3,manifest_count:3,customer_update_ids:xmlIds};
 if(options.badCapture)capture.ok=false;
 if(options.extraScope)capture.children={...children,unexpected:'bad'};
 class GR{
  constructor(table){this.table=table;this.filters=[];this.limit=Infinity;}
  isValid(){return !!db[this.table];}
  isValidField(f){return Object.hasOwn(this.row||{},f);}
  get(id){this.ref=db[this.table]?.find(r=>r.sys_id===id);this.row=this.ref?{...this.ref}:null;return !!this.row;}
  getUniqueValue(){return this.row.sys_id;}
  getRecordClassName(){return this.table;}
  getValue(f){return this.row[f]??'';}
  addQuery(f,op,value){if(arguments.length===2){value=op;op='=';}this.filters.push(r=>op==='IN'?String(value).split(',').includes(String(r[f])):String(r[f]??'')===String(value));}
  setLimit(n){this.limit=n;}
  query(){this.rows=db[this.table].filter(r=>this.filters.every(f=>f(r))).slice(0,this.limit);this.cursor=0;}
  next(){this.ref=this.rows[this.cursor++];this.row=this.ref?{...this.ref}:null;return !!this.row;}
  setValue(k,v){this.row[k]=v;}
  update(){if(options.failSecondUpdate&&writes===1)return null;writes++;Object.assign(this.ref,this.row);return this.row.sys_id;}
 }
 function XML(){this.parseXML=s=>this.xml=s;this.getNodeText=p=>{const f=p.split('/').pop();return(this.xml.match(new RegExp('<'+f+'>([^<]*)</'+f+'>'))||[])[1]||'';};}
 const gs={hasRole:()=>!options.noAdmin,getPreference:()=>options.currentRoot?ROOT:options.currentChild?children.global:'unrelated',info:s=>{output=JSON.parse(s.slice(s.indexOf('{')));}};
 let source=script;
 if(!options.noInput)source=source.replace('var VERIFIED_CAPTURE = null;','var VERIFIED_CAPTURE = '+JSON.stringify(capture)+';').replace('var FROZEN_MANIFEST = [];','var FROZEN_MANIFEST = '+JSON.stringify(frozen)+';');
 vm.runInNewContext(source,{GlideRecord:GR,XMLDocument2:XML,gs});return{output,writes,db};
}
let r=run();assert.equal(r.output.ok,true,r.output.error);assert.equal(r.writes,4);assert(r.db.sys_update_set.every(s=>s.state==='complete'));
r=run({alreadyComplete:true});assert.equal(r.output.ok,true,r.output.error);assert.equal(r.writes,0);
for(const option of ['noInput','noAdmin','badCapture','extraScope','currentRoot','currentChild','staleSource','staleXml','wrongXmlScope','wrongChild','extraXml','extraChild']){
 r=run({[option]:true});assert.equal(r.output.ok,false,option);assert.equal(r.writes,0,option);assert.equal(r.output.status,'not_completed');
}
r=run({failSecondUpdate:true});assert.equal(r.output.ok,false);assert.equal(r.writes,1);assert.equal(r.output.status,'partially changed; inspect set states');
console.log('PASS: verified completion/idempotence; zero-write rejection of missing capture, stale source/XML, wrong scope/set, current set, extra updates/children; partial failure reported.');
