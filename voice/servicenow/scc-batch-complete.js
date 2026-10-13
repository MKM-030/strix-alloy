/* Global Background Script. Inject the successful final capture result and its frozen plan.
 * Completes only the known SCC batch after fresh source/XML/ownership verification.
 * No source, credential, consumer/account, payload or current-set changes.
 */
(function(){
var VERIFIED_CAPTURE = null;
var FROZEN_MANIFEST = [];
var ROOT='194a7413933f0754e7f2b9fa6aba1080',NAME='SCC 2026 - Local Voice + ITSM Laptop Demo - 2026-10-12',MARK='SCC_CAPTURE_MANIFEST_V1_2026_10_12';
var CHILDREN={'32808450431302106c3603295bb8f245':'514a7413933f0754e7f2b9fa6aba109c','7cc4ec81533121106b38ddeeff7b12ee':'d54a7413933f0754e7f2b9fa6aba109e','global':'114a7413933f0754e7f2b9fa6aba10a0'};
var setIds=[ROOT],sets={},expected={},seen={},out={ok:false,batch:ROOT,writes:0,status:'not_started'};sets[ROOT]=true;
try{
if(!gs.hasRole('admin'))fail('Admin required');
var c=VERIFIED_CAPTURE,n=FROZEN_MANIFEST.length;
if(!c||!c.ok||c.batch!==ROOT||!n||n>200||c.captured!==n||c.manifest_count!==n||!c.customer_update_ids||c.customer_update_ids.length!==n)fail('Successful final capture and matching frozen manifest required');
for(var scope in CHILDREN)if(own(CHILDREN,scope)){var id=CHILDREN[scope];setIds.push(id);sets[id]=true;if(!c.children||c.children[scope]!==id)fail('Captured child mismatch');checkSet(id,scope,ROOT);}
for(scope in c.children)if(own(c.children,scope)&&!own(CHILDREN,scope))fail('Unexpected captured scope');
checkSet(ROOT,'global','');notCurrent();
for(var i=0;i<n;i++){var xmlId=String(c.customer_update_ids[i]);if(expected[xmlId])fail('Duplicate captured update ID');expected[xmlId]=true;}
for(i=0;i<n;i++){
 var f=FROZEN_MANIFEST[i];if(f.length!==5||!own(CHILDREN,f[2]))fail('Invalid frozen row');var key=f[0]+':'+f[1];if(seen[key])fail('Duplicate frozen source');seen[key]=true;
 if(/^(sys_cs_consumer|sys_cs_consumer_account|sys_user|sys_user_has_role)$/.test(f[0]))fail('Runtime identity cannot be transported');
 var gr=read(f[0],f[1]),actualScope=gr.isValidField('sys_scope')?String(gr.getValue('sys_scope')||'global'):'global';
 if(String(gr.getRecordClassName())!==f[0]||actualScope!==f[2]||String(gr.getValue('sys_updated_on')||'')!==f[3]||String(gr.getValue('sys_mod_count')||'')!==f[4])fail('Source changed since final capture: '+key);
 var q=new GlideRecord('sys_update_xml');q.addQuery('update_set',CHILDREN[f[2]]);q.addQuery('name',String(gr.getValue('sys_update_name')||f[0]+'_'+f[1]));q.setLimit(2);q.query();
 if(!q.next()||!expected[String(q.getUniqueValue())]||String(q.getValue('application')||'global')!==f[2]||String(q.getValue('action'))==='DELETE')fail('Final customer update mismatch: '+key);
 var doc=new XMLDocument2();doc.parseXML(String(q.getValue('payload')||''));var fields=['sys_id','sys_updated_on','sys_mod_count'],values=[f[1],f[3],f[4]];
 for(var j=0;j<fields.length;j++)if(String(doc.getNodeText('//'+f[0]+'/'+fields[j])||'')!==values[j])fail('Final XML revision mismatch: '+key);if(q.next())fail('Duplicate final customer update: '+key);
}
var h=new GlideRecord('sys_update_set');h.addQuery('parent','IN',setIds.join(','));h.query();while(h.next())if(!sets[String(h.getUniqueValue())]||String(h.getValue('parent'))!==ROOT)fail('Unexpected batch descendant');
var u=new GlideRecord('sys_update_xml');u.addQuery('update_set','IN',setIds.join(','));u.query();var count=0;while(u.next()){if(!expected[String(u.getUniqueValue())])fail('Unexpected batch customer update');count++;}if(count!==n)fail('Final capture count mismatch');
for(scope in CHILDREN)if(own(CHILDREN,scope))complete(CHILDREN[scope],scope,ROOT);
complete(ROOT,'global','');
for(i=0;i<setIds.length;i++)if(String(read('sys_update_set',setIds[i]).getValue('state'))!=='complete')fail('Completion readback failed');
out.ok=true;out.status='complete';out.manifest_count=n;
}catch(e){out.error=String(e.message||e);out.status=out.writes?'partially changed; inspect set states':'not_completed';}
gs.info('[SCC Batch Complete] '+JSON.stringify(out));
function own(o,k){return Object.prototype.hasOwnProperty.call(o,k);}
function fail(message){throw new Error(message);}
function read(table,id){var gr=new GlideRecord(table);if(!gr.isValid()||!gr.get(id)||String(gr.getUniqueValue())!==String(id))fail('Missing exact record '+table+'/'+id);return gr;}
function notCurrent(){if(sets[String(gs.getPreference('sys_update_set')||'')])fail('Select an unrelated current update set before completing the SCC batch');}
function checkSet(id,scope,parent){var gr=read('sys_update_set',id),name=String(gr.getValue('name')||''),state=String(gr.getValue('state'));
 if(String(gr.getValue('application'))!==scope||String(gr.getValue('parent')||'')!==parent||String(gr.getValue('description')||'').indexOf(MARK)<0||(parent?name.indexOf(NAME+' / ')!==0:name!==NAME)||(state!=='in progress'&&state!=='complete'))fail('Owned batch set mismatch '+id);
 if(parent&&gr.isValidField('batch_base')&&String(gr.getValue('batch_base'))!==ROOT)fail('Batch base mismatch');return gr;}
function complete(id,scope,parent){notCurrent();var gr=checkSet(id,scope,parent);if(String(gr.getValue('state'))==='complete')return;gr.setValue('state','complete');if(!gr.update())fail('Could not complete '+id);out.writes++;if(String(read('sys_update_set',id).getValue('state'))!=='complete')fail('Completion failed '+id);}
})();
