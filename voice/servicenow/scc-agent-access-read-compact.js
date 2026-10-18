/* Read only: exact SCC agent user/data access records. */
(function(){
var ids=['a4a9438393738354e7f2b9fa6aba101d','e850ba4f933b4354e7f2b9fa6aba105d'],names=[],aclIds=[],cfgIds=[];
var out={writes:0,agents:[],acl:[],roles:[],config:[],mapping:[],gaps:[]};
for(var i=0;i<ids.length;i++){var a=new GlideRecord('sn_aia_agent');if(!a.get(ids[i]))throw new Error('Agent missing: '+ids[i]);out.agents.push(row(a,['name','internal_name']));var name=String(a.getValue('internal_name')||'');if(!name)throw new Error('Agent internal_name missing');names.push(name);}
var acl=query('sys_security_acl',[['name','IN',names.join(',')]]);
if(acl)while(acl.next()){aclIds.push(String(acl.getUniqueValue()));out.acl.push(row(acl,['name','type','operation','active','admin_overrides','decision_type','condition']));}
if(aclIds.length){var ar=query('sys_security_acl_role',[['sys_security_acl','IN',aclIds.join(',')]]);if(ar)while(ar.next()){var r=row(ar,['sys_security_acl','sys_user_role']);r.role_name=ar.getDisplayValue('sys_user_role');out.roles.push(r);}}
var cfg=query('sys_agent_access_role_configuration',[['agent_table','sn_aia_agent'],['agent','IN',ids.join(',')]]);
if(cfg)while(cfg.next()){cfgIds.push(String(cfg.getUniqueValue()));out.config.push(row(cfg,['name','agent_table','agent','action','allow_all_session_roles','role_list']));}
if(cfgIds.length){var m=query('sys_agent_access_role_mapping',[['agent_access_config','IN',cfgIds.join(',')]]);if(m)while(m.next()){var mr=row(m,['agent_access_config','role']);mr.role_name=m.getDisplayValue('role');out.mapping.push(mr);}}
gs.info('[SCC Agent Access Read] '+JSON.stringify(out));
function row(gr,fields){var r={table:String(gr.getRecordClassName()),sys_id:String(gr.getUniqueValue())};fields=fields.concat(['sys_scope','sys_created_on','sys_created_by','sys_updated_on','sys_mod_count']);for(var n=0;n<fields.length;n++)if(gr.isValidField(fields[n]))r[fields[n]]=String(gr.getValue(fields[n])||'');return r;}
function query(table,filters){var gr=new GlideRecord(table);if(!gr.isValid()){out.gaps.push('Missing table '+table);return null;}for(var n=0;n<filters.length;n++){var f=filters[n];if(!gr.isValidField(f[0])){out.gaps.push('Missing field '+table+'.'+f[0]);return null;}if(f.length===2)gr.addQuery(f[0],f[1]);else gr.addQuery(f[0],f[1],f[2]);}gr.setLimit(51);gr.query();if(gr.getRowCount()>50)throw new Error('Read limit: '+table);return gr;}
})();
