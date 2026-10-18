/* Global Background Script. Inject the just-reviewed full plan's frozen_manifest_candidate.
 * Captures only that exact manifest; no rediscovery or source edits. All sets remain WIP.
 */
(function(){
var FROZEN_MANIFEST = [];
var NAME='SCC 2026 - Local Voice + ITSM Laptop Demo - 2026-10-12',MARK='SCC_CAPTURE_MANIFEST_V1_2026_10_12';
var excluded={'6882f6c7937b4354e7f2b9fa6aba105e':1,'5782fac7937b4354e7f2b9fa6aba10ea':1,'60b9ea4893c68350e7f2b9fa6aba1090':1,'5287ce9c93d64f145c8132d47aba1060':1};
var rows=[],seen={},scopes={},children={},captured=[],expected={},batch='',changed=false;
var original=String(gs.getPreference('sys_update_set')||''),out={ok:false,status:'not_started'};
try{
if(!gs.hasRole('admin'))fail('Admin required');
if(!original)fail('Select a current update set first');
if(!FROZEN_MANIFEST.length||FROZEN_MANIFEST.length>200)fail('Reviewed frozen manifest required; limit 200');
for(var i=0;i<FROZEN_MANIFEST.length;i++){
 var f=FROZEN_MANIFEST[i];if(f.length!==5)fail('Frozen row must have table, ID, scope, updated_on, mod_count');
 var key=f[0]+':'+f[1];if(seen[key])fail('Duplicate frozen record '+key);seen[key]=true;
 var gr=source(f);noSecrets(gr);
 var entry={f:f,name:String(gr.getValue('sys_update_name')||f[0]+'_'+f[1])};rows.push(entry);
 if(!scopes[f[2]]){var scope=read('sys_scope',f[2]);scopes[f[2]]=String(scope.getValue('scope')||scope.getValue('name')||f[2]);}
}
rows.sort(function(a,b){return a.f[2]+a.f[0]+a.f[1]<b.f[2]+b.f[0]+b.f[1]?-1:1;});
batch=ensureSet(NAME,'global','');
for(var s in scopes)if(own(scopes,s))children[s]=ensureSet(NAME+' / '+scopes[s],s,batch);
var active='',manager;
for(i=0;i<rows.length;i++){
 var e=rows[i],scopeId=e.f[2];
 if(scopeId!==active){changed=true;new GlideUpdateSet().set(children[scopeId]);if(String(gs.getPreference('sys_update_set')||'')!==children[scopeId])fail('Update set selection failed: '+scopeId);manager=new GlideUpdateManager2();active=scopeId;}
 gr=source(e.f);noSecrets(gr);
 if(String(gr.getValue('sys_update_name')||e.f[0]+'_'+e.f[1])!==e.name)fail('Update identity changed: '+e.f[0]+'/'+e.f[1]);
 manager.saveRecord(gr);
 var xmlId=verify(e,children[scopeId]);e.xml_id=xmlId;captured.push(xmlId);expected[xmlId]=true;
}
audit();restore();out.ok=true;out.status='in progress';
}catch(error){out.error=String(error.message||error);out.status=batch?'requires review':'not_started';}
finally{if(changed)try{restore();}catch(restoreError){out.ok=false;out.status='requires review';out.restore_error='Could not restore current update set '+original;}
out.batch=batch;out.children=children;out.manifest_count=rows.length;out.captured=captured.length;out.customer_update_ids=captured;gs.info('[SCC Frozen Capture] '+JSON.stringify(out));}
function own(obj,key){return Object.prototype.hasOwnProperty.call(obj,key);}
function fail(message){throw new Error(message);}
function open(table){var gr=new GlideRecord(table);if(!gr.isValid())fail('Missing table '+table);return gr;}
function read(table,id){var gr=open(table);if(!gr.get(id)||String(gr.getUniqueValue())!==String(id))fail('Missing exact record '+table+'/'+id);return gr;}
function source(f){
 if(excluded[f[1]]||/(credential|oauth|token|password|secret|certificate|private_key|execution|session|conversation|message_log|audit|history|cache|runtime)/i.test(f[0]))fail('Excluded source '+f[0]+'/'+f[1]);
 var gr=read(f[0],f[1]),scope=gr.isValidField('sys_scope')?String(gr.getValue('sys_scope')||'global'):'global';
 if(String(gr.getRecordClassName())!==f[0]||scope!==f[2]||String(gr.getValue('sys_updated_on')||'')!==f[3]||String(gr.getValue('sys_mod_count')||'')!==f[4])fail('Source differs from frozen plan: '+f[0]+'/'+f[1]);return gr;
}
function restore(){if(!changed)return;new GlideUpdateSet().set(original);if(String(gs.getPreference('sys_update_set')||'')!==original)fail('Restore failed');changed=false;}
function ensureSet(name,scope,parent){
 var q=open('sys_update_set');q.addQuery('name',name);q.setLimit(2);q.query();
 if(q.next()){var id=String(q.getUniqueValue());if(String(q.getValue('application'))!==scope||String(q.getValue('parent')||'')!==parent||String(q.getValue('description')||'').indexOf(MARK)<0||String(q.getValue('state'))!=='in progress')fail('Existing set differs: '+name);if(q.next())fail('Duplicate set name '+name);return id;}
 q.initialize();q.setValue('name',name);q.setValue('application',scope);q.setValue('state','in progress');if(parent)q.setValue('parent',parent);q.setValue('description',MARK+'\nSCC reviewed exact configuration manifest. WIP. Credentials excluded; destination prerequisites documented separately.');var created=String(q.insert()||'');if(!created)fail('Cannot create set '+name);return created;
}
function verify(e,setId){
 var q=open('sys_update_xml');q.addQuery('update_set',setId);q.addQuery('name',e.name);q.setLimit(2);q.query();if(!q.next())fail('Customer update missing '+e.name);
 var id=String(q.getUniqueValue());if(String(q.getValue('application')||'global')!==e.f[2]||String(q.getValue('action'))==='DELETE')fail('Capture application/action mismatch '+e.name);
 var doc=new XMLDocument2();doc.parseXML(String(q.getValue('payload')||''));var fields=['sys_id','sys_updated_on','sys_mod_count'],values=[e.f[1],e.f[3],e.f[4]];
 for(var n=0;n<fields.length;n++)if(String(doc.getNodeText('//'+e.f[0]+'/'+fields[n])||'')!==values[n])fail('Captured source identity/revision mismatch '+e.name+'.'+fields[n]);if(q.next())fail('Duplicate customer update '+e.name);return id;
}
function audit(){
 var ids=[batch],known={};known[batch]=true;
 for(var scope in children)if(own(children,scope)){var id=children[scope];ids.push(id);known[id]=true;var child=read('sys_update_set',id);if(String(child.getValue('parent'))!==batch||String(child.getValue('application'))!==scope||String(child.getValue('state'))!=='in progress')fail('Child set mismatch '+id);if(child.isValidField('batch_base')&&String(child.getValue('batch_base'))!==batch)fail('Batch base mismatch '+id);}
 if(String(read('sys_update_set',batch).getValue('state'))!=='in progress')fail('Parent set no longer WIP');
 var q=open('sys_update_set');q.addQuery('parent','IN',ids.join(','));q.query();while(q.next())if(!known[String(q.getUniqueValue())]||String(q.getValue('parent'))!==batch)fail('Unexpected batch descendant '+q.getUniqueValue());
 q=open('sys_update_xml');q.addQuery('update_set','IN',ids.join(','));q.query();var count=0;
 while(q.next()){if(!expected[String(q.getUniqueValue())])fail('Unexpected customer update '+q.getUniqueValue());count++;xmlSecrets(String(q.getValue('payload')||''),String(q.getUniqueValue()));}
 if(count!==rows.length)fail('Batch capture count mismatch');
 for(var i=0;i<rows.length;i++){source(rows[i].f);if(verify(rows[i],children[rows[i].f[2]])!==rows[i].xml_id)fail('Captured update replaced during audit');}
}
function noSecrets(gr){
 var elements=gr.getElements();for(var i=0;i<elements.size();i++){var element=elements.get(i),field=String(element.getName()),value=String(gr.getValue(field)||'');if(!value)continue;var type=String(element.getED().getInternalType()),ref=type==='reference'||type==='glide_list';
 if(/(password|encrypted|secret)/i.test(type)||(!ref&&/(^|_)(password|client_secret|api_key|access_token|refresh_token|auth_token|bearer_token|private_key|shared_secret|shared_key|hmac_key|secret)($|_)/i.test(field)))fail('Secret-bearing field blocks capture: '+gr.getRecordClassName()+'/'+gr.getUniqueValue()+'.'+field);
 if(/"(?:password|client_secret|api_key|access_token|refresh_token|auth_token|bearer_token|private_key|shared_secret|shared_key|hmac_key|secret)"\s*:\s*"[^"\s][^"]*"/i.test(value)||/-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/.test(value)||/^Bearer\s+\S{12,}/i.test(value))fail('Embedded secret blocks capture: '+gr.getRecordClassName()+'/'+gr.getUniqueValue()+'.'+field);}
}
function xmlSecrets(payload,id){var re=/<(password|client_secret|api_key|access_token|refresh_token|auth_token|bearer_token|private_key|shared_secret|shared_key|hmac_key|secret)(?:\s[^>]*)?>([\s\S]*?)<\/\1\s*>/ig,m;while((m=re.exec(payload))){var value=m[2].replace(/^\s*<!\[CDATA\[([\s\S]*)\]\]>\s*$/,'$1');if(value.replace(/\s/g,''))fail('Secret-bearing customer update '+id);}}
})();
